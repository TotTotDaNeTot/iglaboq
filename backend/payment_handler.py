from flask import Flask
from flask_cors import CORS

from yookassa import Configuration, Payment

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import *
from aiogram.fsm.storage.memory import MemoryStorage

import aiomysql
import aiohttp
from aiohttp import web

import asyncio


from services.email_service import email_service
from services.bot_notifications import send_telegram_payment_async

import logging
import uuid
import sys
import os
import requests




app = Flask(__name__)
CORS(app)  # Разрешаем все CORS-запросы


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



# Конфигурация ЮKassa
Configuration.account_id = os.getenv('YOOKASSA_SHOP_ID')
Configuration.secret_key = os.getenv('YOOKASSA_SECRET_KEY')

YOOKASSA_SHOP_ID = os.getenv('YOOKASSA_SHOP_ID')
YOOKASSA_SECRET_KEY = os.getenv('YOOKASSA_SECRET_KEY')


bot = Bot(
    token=os.getenv('BOT_TOKEN'),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)


storage = MemoryStorage()
dp = Dispatcher(bot=bot, storage=storage)


# Пул соединений MySQL
db_pool = None


async_db_pool = None
app = web.Application()



async def init_async_db():
    global async_db_pool
    try:
        async_db_pool = await aiomysql.create_pool(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('PASSWORD'),
            db=os.getenv('DB_NAME'),
            port=int(os.getenv('DB_PORT')),
            minsize=5,
            maxsize=10,
            autocommit=False
        )
        logger.info("✅ Успешное создание асинхронного пула MySQL")
    except Exception as e:
        logger.error(f"❌ Ошибка создания асинхронного пула MySQL: {e}")
        raise
    


async def get_async_db():
    return await async_db_pool.acquire()



async def release_async_db(conn):
    await async_db_pool.release(conn)
    
    


async def create_payment(request):
    conn = None
    cursor = None
    try:
        data = await request.json()
        if not data:
            return web.json_response({"success": False, "error": "No data provided"}, status=400)

        required_fields = ['user_id', 'amount', 'journal_id', 'quantity']
        for field in required_fields:
            if field not in data:
                return web.json_response({"success": False, "error": f"Missing required field: {field}"}, status=400)

        user_id = data['user_id']
        journal_id = data['journal_id']
        quantity = int(data['quantity'])
        amount = float(data['amount'])
        
        if quantity <= 0:
            return web.json_response({"success": False, "error": "Quantity must be positive"}, status=400)

        # Асинхронное подключение
        conn = await async_db_pool.acquire()
        cursor = await conn.cursor(aiomysql.DictCursor)
        
        # НАЧИНАЕМ ТРАНЗАКЦИЮ (БЕЗ БЛОКИРОВОК)
        await conn.begin()
        
        # 1. АТОМАРНОЕ ВЫЧИТАНИЕ quantity БЕЗ БЛОКИРОВКИ
        await cursor.execute(
            "UPDATE journals SET quantity = quantity - %s WHERE id = %s AND quantity >= %s",
            (quantity, journal_id, quantity)
        )
        
        # Проверяем, получилось ли вычесть
        if cursor.rowcount == 0:
            await conn.rollback()
            await async_db_pool.release(conn)
            
            # Узнаем текущее количество для информативного сообщения
            await cursor.execute("SELECT quantity FROM journals WHERE id = %s", (journal_id,))
            journal = await cursor.fetchone()
            
            if journal:
                available = journal['quantity']
                return web.json_response({
                    "success": False,
                    "error": f"Not enough items in stock. Available: {available}, requested: {quantity}"
                }, status=400)
            else:
                return web.json_response({"success": False, "error": "Journal not found"}, status=404)
        
        # 2. Создаем платеж в ЮKassa (асинхронно через aiohttp)
        payment_data = {
            "amount": {
                "value": f"{amount:.2f}",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/CocoCamBot"
            },
            "capture": True,
            "metadata": {
                "user_id": user_id,
                "journal_id": journal_id,
                "quantity": quantity,
                **{k: data.get(k, '') for k in ['fullname', 'city', 'postcode', 'phone', 'email', 'chat_id']}
            },
            "description": f"Оплата журнала ID {journal_id}"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://api.yookassa.ru/v3/payments',
                json=payment_data,
                auth=aiohttp.BasicAuth(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
                headers={'Idempotence-Key': str(uuid.uuid4())}
            ) as response:
                payment = await response.json()
        
        # 3. Сохраняем информацию о платеже
        await cursor.execute(
            """INSERT INTO payments 
            (payment_id, user_id, journal_id, amount, status) 
            VALUES (%s, %s, %s, %s, %s)""",
            (payment['id'], user_id, journal_id, amount, 'pending')
        )
        
        # 4. 🔥 АВТОМАТИЧЕСКОЕ ПОДТВЕРЖДЕНИЕ ПЛАТЕЖА
        if payment['status'] == 'waiting_for_capture':
            try:
                logger.info(f"Auto-capturing payment {payment['id']}")
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f'https://api.yookassa.ru/v3/payments/{payment["id"]}/capture',
                        json={"amount": {"value": f"{amount:.2f}", "currency": "RUB"}},
                        auth=aiohttp.BasicAuth(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
                        headers={'Idempotence-Key': str(uuid.uuid4())}
                    ) as response:
                        capture_result = await response.json()
                        
                logger.info(f"Capture result: {capture_result['status']}")
                
                # Обновляем статус в БД
                await cursor.execute(
                    "UPDATE payments SET status = %s WHERE payment_id = %s",
                    (capture_result['status'], payment['id'])
                )
                
                # Если платеж успешен - создаем заказ
                if capture_result['status'] == 'succeeded':
                    await cursor.execute(
                        """INSERT INTO orders (tg_user_id, fullname, city, postcode, 
                            phone, email, product_id, quantity, amount, payment_id, status, currency)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'paid', 'RUB')""",
                        (
                            user_id,
                            data.get('fullname', ''),
                            data.get('city', ''),
                            data.get('postcode', ''),
                            data.get('phone', ''),
                            data.get('email', ''),
                            journal_id,
                            quantity,
                            amount,
                            payment['id']
                        )
                    )
                    
            except Exception as e:
                logger.error(f"Auto-capture failed: {str(e)}")
                # Откатываем списание товара при ошибке
                await cursor.execute(
                    "UPDATE journals SET quantity = quantity + %s WHERE id = %s",
                    (quantity, journal_id)
                )
                await conn.rollback()
                await async_db_pool.release(conn)
                return web.json_response({"success": False, "error": f"Payment capture failed: {str(e)}"}, status=500)
        
        await conn.commit()
        await async_db_pool.release(conn)
        
        return web.json_response({
            "success": True,
            "payment_url": payment['confirmation']['confirmation_url'],
            "payment_id": payment['id'],
            "status": payment['status']
        })

    except Exception as e:
        if conn:
            await conn.rollback()
            await async_db_pool.release(conn)
        logger.error(f"Payment processing error: {str(e)}", exc_info=True)
        return web.json_response({"success": False, "error": str(e)}, status=500)
    finally:
        if cursor:
            await cursor.close()
            
            


async def payment_webhook(request):
    logger.info("Webhook received")
    
    conn = None
    cursor = None
    
    try:
        event_json = await request.json()
        payment = event_json['object']
        payment_id = payment['id']
        status = payment['status']
        metadata = payment.get('metadata', {})
        
        logger.info(f"Payment {payment_id}, status: {status}")
        
        # Асинхронное подключение
        conn = await async_db_pool.acquire()
        cursor = await conn.cursor(aiomysql.DictCursor)
        await conn.begin()
        
        # КРИТИЧЕСКАЯ ЧАСТЬ: БЛОКИРУЕМ ТОЛЬКО ДЛЯ ПРОВЕРКИ УВЕДОМЛЕНИЯ
        await cursor.execute(
            """SELECT p.status, p.processed, p.notification_sent, p.amount, p.user_id, p.journal_id
               FROM payments p 
               WHERE p.payment_id = %s FOR UPDATE""",
            (payment_id,)
        )
        existing_payment = await cursor.fetchone()
        
        if not existing_payment:
            await conn.rollback()
            await async_db_pool.release(conn)
            logger.error(f"Payment {payment_id} not found in database")
            return web.json_response({"status": "payment not found"}, status=404)
        
        # ЕСЛИ ПЛАТЕЖ УЖЕ ОБРАБОТАН - ВЫХОДИМ
        if existing_payment.get('processed'):
            await conn.rollback()
            await async_db_pool.release(conn)
            logger.info(f"Payment {payment_id} already processed - skipping")
            return web.json_response({"status": "already_processed"}, status=200)
            
        # ЕСЛИ УЖЕ В КОНЕЧНОМ СТАТУСЕ - ОБНОВЛЯЕМ processed И ВЫХОДИМ
        if existing_payment['status'] in ['succeeded', 'canceled', 'failed']:
            await cursor.execute(
                "UPDATE payments SET processed = TRUE WHERE payment_id = %s",
                (payment_id,)
            )
            await conn.commit()
            await async_db_pool.release(conn)
            logger.info(f"Payment {payment_id} already finalized - marking processed")
            return web.json_response({"status": "already_finalized"}, status=200)
        
        # ПРОВЕРКА ОБЯЗАТЕЛЬНЫХ ДАННЫХ
        if not all(key in metadata for key in ['chat_id', 'journal_id', 'quantity']):
            await conn.rollback()
            await async_db_pool.release(conn)
            logger.error("Missing required metadata fields")
            return web.json_response({"error": "Missing metadata"}, status=400)

        # ПОЛУЧАЕМ ДАННЫЕ ИЗ METADATA
        quantity = int(metadata['quantity'])
        journal_id = int(metadata['journal_id'])
        amount = float(metadata.get('amount', existing_payment['amount']))
        user_id = existing_payment['user_id']
        
        # ОБРАБОТКА РАЗНЫХ СТАТУСОВ (БЕЗ БЛОКИРОВОК)
        if status == 'waiting_for_capture':
            logger.info(f"Payment {payment_id} waiting for capture - capturing...")
            
            try:
                # Асинхронный захват платежа
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f'https://api.yookassa.ru/v3/payments/{payment_id}/capture',
                        json={"amount": {"value": f"{amount:.2f}", "currency": "RUB"}},
                        auth=aiohttp.BasicAuth(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
                        headers={'Idempotence-Key': str(uuid.uuid4())}
                    ) as response:
                        capture_result = await response.json()
                logger.info(f"Payment captured: {capture_result['status']}")
                
            except Exception as e:
                # ВОЗВРАЩАЕМ ТОВАР ПРИ ОШИБКЕ ЗАХВАТА
                await cursor.execute(
                    "UPDATE journals SET quantity = quantity + %s WHERE id = %s",
                    (quantity, journal_id)
                )
                await cursor.execute(
                    "UPDATE payments SET status = 'failed', processed = TRUE WHERE payment_id = %s",
                    (payment_id,)
                )
                await conn.commit()
                await async_db_pool.release(conn)
                logger.error(f"Capture failed: {str(e)}")
                return web.json_response({"error": f"Capture failed: {str(e)}"}, status=500)
            
            # СОХРАНЯЕМ ЗАКАЗ
            await cursor.execute(
                """INSERT INTO orders (tg_user_id, fullname, city, postcode, 
                    phone, email, product_id, quantity, amount, payment_id, status, currency)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'paid', 'RUB')""",
                (
                    user_id,
                    metadata.get('fullname', ''),
                    metadata.get('city', ''),
                    metadata.get('postcode', ''),
                    metadata.get('phone', ''),
                    metadata.get('email', ''),
                    journal_id,
                    quantity,
                    amount,
                    payment_id
                )
            )
            
            await cursor.execute(
                "UPDATE payments SET status = 'succeeded', processed = TRUE WHERE payment_id = %s",
                (payment_id,)
            )
            
        elif status == 'succeeded':
            logger.info(f"Payment {payment_id} already succeeded")
            
            await cursor.execute(
                """INSERT INTO orders (tg_user_id, fullname, city, postcode, 
                    phone, email, product_id, quantity, amount, payment_id, status, currency)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'paid', 'RUB')""",
                (
                    user_id,
                    metadata.get('fullname', ''),
                    metadata.get('city', ''),
                    metadata.get('postcode', ''),
                    metadata.get('phone', ''),
                    metadata.get('email', ''),
                    journal_id,
                    quantity,
                    amount,
                    payment_id
                )
            )
            
            await cursor.execute(
                "UPDATE payments SET status = 'succeeded', processed = TRUE WHERE payment_id = %s",
                (payment_id,)
            )
            
        elif status in ['canceled', 'failed']:
            logger.info(f"Payment {payment_id} {status} - returning goods")
            
            await cursor.execute(
                "UPDATE journals SET quantity = quantity + %s WHERE id = %s",
                (quantity, journal_id)
            )
            
            await cursor.execute(
                "UPDATE payments SET status = %s, processed = TRUE WHERE payment_id = %s",
                (status, payment_id)
            )
        
        # КРИТИЧЕСКАЯ ЧАСТЬ: ОТПРАВКА УВЕДОМЛЕНИЯ С БЛОКИРОВКОЙ
        # Еще раз проверяем под блокировкой, не отправили ли уже
        await cursor.execute(
            "SELECT notification_sent FROM payments WHERE payment_id = %s FOR UPDATE",
            (payment_id,)
        )
        notification_check = await cursor.fetchone()
        
        if not notification_check or not notification_check.get('notification_sent'):
            # ОТПРАВЛЯЕМ УВЕДОМЛЕНИЕ ТОЛЬКО ОДИН РАЗ
            if status in ['succeeded', 'waiting_for_capture']:
                success = await send_telegram_payment_async(
                    chat_id=metadata['chat_id'],
                    payment_id=payment_id,
                    amount=amount,
                    product_id=journal_id,
                    customer_name=metadata.get('fullname'),
                    delivery_city=metadata.get('city'),
                    delivery_postcode=metadata.get('postcode')
                )
                
                # 2. Отправляем на email через EmailService
                email_success = await email_service.send_order_confirmation(
                    payment_id=payment_id,
                    amount=amount,
                    product_id=journal_id,
                    metadata=metadata
                )
                
                if success or email_success:
                    # Помечаем как отправленное
                    await cursor.execute(
                        "UPDATE payments SET notification_sent = TRUE WHERE payment_id = %s",
                        (payment_id,)
                    )
        
        await conn.commit()
        await async_db_pool.release(conn)
        logger.info(f"Payment {payment_id} processed successfully")
        return web.json_response({"status": "ok"}, status=200)
        
    except Exception as e:
        if conn: 
            await conn.rollback()
            await async_db_pool.release(conn)
        logger.error(f"Webhook error: {str(e)}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)
    finally:
        if cursor: 
            await cursor.close()
            


def capture_payment(payment_id, amount):
    """Подтверждает платеж в ЮKassa"""
    try:
        shop_id = os.getenv('YOOKASSA_SHOP_ID')
        secret_key = os.getenv('YOOKASSA_SECRET_KEY')
        
        if not shop_id or not secret_key:
            raise ValueError("YKassa credentials not set")
            
        url = f"https://api.yookassa.ru/v3/payments/{payment_id}/capture"
        
        auth = (shop_id, secret_key)
        headers = {
            'Idempotence-Key': str(uuid.uuid4()),
            'Content-Type': 'application/json'
        }
        
        # Обязательно указываем amount для подтверждения
        payload = {
            "amount": {
                "value": f"{amount:.2f}",
                "currency": "RUB"
            }
        }
        
        logger.info(f"Capturing payment {payment_id} with amount {amount}")
        
        response = requests.post(url, auth=auth, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"Capture successful: {result['status']}")
        return result
        
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error capturing payment: {e.response.status_code} - {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"Error capturing payment {payment_id}: {str(e)}")
        raise
        
        


def update_payment_status(payment_id: str, status: str) -> int:
    """Обновляет статус платежа и возвращает количество обновленных строк"""
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE payments SET status = %s, updated_at = NOW() WHERE payment_id = %s",
            (status, payment_id)
        )
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        logger.error(f"Database update error: {e}")
        raise
    finally:
        if cursor: cursor.close()
        if conn: conn.close()





# async def check_payment_status_in_db(payment_id: str) -> Optional[dict]:
#     """Проверяет статус платежа в базе данных"""
#     try:
#         conn = db.get_connection()
#         cursor = conn.cursor(dictionary=True)
#         cursor.execute(
#             "SELECT * FROM payments WHERE payment_id = %s",
#             (payment_id,)
#         )
#         payment = cursor.fetchone()
#         cursor.close()
#         conn.close()
#         return payment
#     except Exception as e:
#         logger.error(f"Database error checking payment: {e}")
#         return None

    
    
async def debug_payment(request):
    try:
        # Получаем параметр из URL
        payment_ref = request.match_info['payment_ref']
        
        # Ваша логика обработки
        conn = await async_db_pool.acquire()
        cursor = await conn.cursor(aiomysql.DictCursor)
        
        await cursor.execute(
            "SELECT * FROM payments WHERE payment_id = %s",
            (payment_ref,)
        )
        payment = await cursor.fetchone()
        
        await async_db_pool.release(conn)
        
        if payment:
            return web.json_response({
                "success": True,
                "payment": payment
            })
        else:
            return web.json_response({
                "success": False,
                "error": "Payment not found"
            }, status=404)
            
    except Exception as e:
        logger.error(f"Debug error: {str(e)}")
        return web.json_response({
            "success": False,
            "error": str(e)
        }, status=500)
        
    

app.router.add_post('/create_payment', create_payment)
app.router.add_post('/payment_webhook', payment_webhook)
app.router.add_get('/debug/payment/{payment_ref}', debug_payment)



# Middleware для обработки CORS
@web.middleware
async def cors_middleware(request, handler):
    # Обрабатываем OPTIONS запросы
    if request.method == 'OPTIONS':
        response = web.Response()
    else:
        response = await handler(request)
    
    # Добавляем CORS headers
    response.headers.update({
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, GET, OPTIONS, PUT, DELETE',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Allow-Credentials': 'true'
    })
    return response

# Создаем приложение с middleware
app = web.Application(middlewares=[cors_middleware])


# Явный обработчик для OPTIONS запросов
async def options_handler(request):
    return web.Response(status=200)


async def main():
    await init_async_db()
    
    # Добавляем маршруты
    app.router.add_post('/create_payment', create_payment)
    app.router.add_post('/payment_webhook', payment_webhook)
    app.router.add_get('/debug/payment/{payment_ref}', debug_payment)
    
    # Добавляем OPTIONS handlers для всех маршрутов
    app.router.add_options('/create_payment', options_handler)
    app.router.add_options('/payment_webhook', options_handler)
    app.router.add_options('/debug/payment/{payment_ref}', options_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 5005)
    await site.start()
    
    logger.info("🚀 Сервер запущен на http://0.0.0.0:5005")
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
            


