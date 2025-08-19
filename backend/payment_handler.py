from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import *

from dotenv import load_dotenv


from flask import Flask, request, jsonify, redirect
from flask_cors import CORS

import logging
import uuid
import sys
import os
import requests
import json
import asyncio

from gunicorn.glogging import Logger
from yookassa import Configuration, Payment
from aiomysql import create_pool
from aiogram.fsm.storage.memory import MemoryStorage

from database import db 

import mysql.connector
from mysql.connector import pooling

from yookassa import Payment


app = Flask(__name__)
CORS(app)  # Разрешаем все CORS-запросы

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



# Конфигурация ЮKassa
Configuration.account_id = os.getenv('YOOKASSA_SHOP_ID')
Configuration.secret_key = os.getenv('YOOKASSA_SECRET_KEY')


bot = Bot(
    token=os.getenv('BOT_TOKEN'),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)


storage = MemoryStorage()
dp = Dispatcher(bot=bot, storage=storage)


# Пул соединений MySQL
db_pool = None


def init_db():
    global db_pool
    try:
        db_pool = pooling.MySQLConnectionPool(
            pool_name="mamp_pool",
            pool_size=5,
            host='127.0.0.1',
            user='root',
            password='root',
            database='tg_bot',
            port=8889,
            auth_plugin='mysql_native_password'
        )
        logger.info("✅ Успешное подключение к MAMP MySQL")
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к MAMP MySQL: {e}")
        raise

def get_db_conn():
    return db_pool.get_connection()



# @app.route('/create_payment', methods=['POST'])
# def create_payment():
#     try:
#         data = request.json
#         user_id = data['user_id']
#         chat_id = data.get('chat_id', user_id)
#         amount = float(data['amount'])
#         journal_id = data.get('journal_id')
        
#         if not journal_id:
#             return jsonify({"success": False, "error": "Journal ID is required"}), 400

#         # Создаем платеж в ЮKassa
#         payment = Payment.create({
#             "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
#             "confirmation": {
#                 "type": "redirect",
#                 "return_url": "https://t.me/CocoCamBot"
#             },
#             "capture": True,
#             "metadata": {
#                 "user_id": user_id,
#                 "chat_id": chat_id,
#                 "journal_id": journal_id,
#                 "fullname": data.get('fullname', ''),
#                 "city": data.get('city', ''),
#                 "postcode": data.get('postcode', ''),
#                 "phone": data.get('phone', ''),
#                 "email": data.get('email', ''),
#                 "quantity": data.get('quantity', 1)
#             }
#         })

#         # Сохраняем только в payments
#         conn = db_pool.get_connection()
#         cursor = conn.cursor()
#         cursor.execute(
#             """INSERT INTO payments 
#             (payment_id, user_id, chat_id, journal_id, amount, status) 
#             VALUES (%s, %s, %s, %s, %s, %s)""",
#             (payment.id, user_id, chat_id, journal_id, amount, 'pending')
#         )
#         conn.commit()
#         cursor.close()
#         conn.close()

#         return jsonify({
#             "success": True,
#             "payment_url": payment.confirmation.confirmation_url,
#             "payment_id": payment.id
#         })
#     except Exception as e:
#         logger.error(f"Payment creation failed: {e}")
#         return jsonify({"success": False, "error": str(e)}), 500
    
    

# @app.route('/payment_webhook', methods=['POST'])
# def payment_webhook():
#     try:
#         logger.info(f"Raw webhook data: {request.data}")
#         event_json = request.json
#         payment = event_json['object']
        
#         logger.info(f"Webhook received for payment: {payment['id']}, status: {payment['status']}")
        
#         if payment['status'] == 'succeeded':
#             metadata = payment.get('metadata', {})
#             user_id = metadata.get('user_id')
#             chat_id = metadata.get('chat_id', user_id)
#             journal_id = metadata.get('journal_id')
#             amount = float(payment['amount']['value'])
            
#             # Получаем данные доставки
#             fullname = metadata.get('fullname', 'Не указано')
#             city = metadata.get('city', 'Не указано')
#             postcode = metadata.get('postcode', 'Не указано')
#             phone = metadata.get('phone', 'Не указано')
#             email = metadata.get('email', 'Не указано')
#             quantity = int(metadata.get('quantity'))
            
#             conn = db_pool.get_connection()
#             cursor = conn.cursor(dictionary=True)
            
#             try:
#                 # Сохраняем заказ в таблицу orders
#                 cursor.execute(
#                     """INSERT INTO orders (
#                         tg_user_id, 
#                         tg_username, 
#                         fullname,
#                         city,
#                         postcode,
#                         phone, 
#                         email, 
#                         product_id, 
#                         quantity, 
#                         amount, 
#                         payment_id, 
#                         status,
#                         currency,
#                         is_test
#                     ) VALUES (
#                         %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
#                     )""",
#                     (
#                         user_id,
#                         None,  # tg_username можно получить из Telegram API
#                         fullname,
#                         city,
#                         postcode,
#                         phone,
#                         email,
#                         journal_id,
#                         quantity,
#                         amount,
#                         payment['id'],
#                         'paid',
#                         payment['amount']['currency'],
#                         payment.get('test', False)
#                     )
#                 )
#                 conn.commit()
                
#                 logger.info(f"Order saved for payment {payment['id']}")
                
#                 # Обновляем статус платежа
#                 cursor.execute(
#                     "UPDATE payments SET status = 'succeeded' WHERE payment_id = %s",
#                     (payment['id'],)
#                 )
#                 conn.commit()
                
#                 # Отправляем уведомление (исправленный вызов)
#                 if chat_id:
#                     send_telegram_notification(
#                         chat_id=chat_id,
#                         payment_id=payment['id'],
#                         amount=amount,
#                         product_id=journal_id,
#                         customer_name=fullname,
#                         delivery_city=city,
#                         delivery_postcode=postcode
#                     )
                    
#             except Exception as db_error:
#                 conn.rollback()
#                 logger.error(f"Database error: {str(db_error)}")
#                 raise
                
#             finally:
#                 cursor.close()
#                 conn.close()
                
#         return jsonify({"status": "ok"}), 200
        
#     except Exception as e:
#         logger.error(f"Webhook processing error: {str(e)}", exc_info=True)
#         return jsonify({"error": str(e)}), 500
    
    
    
    
@app.route('/create_payment', methods=['POST'])
def create_payment():
    conn = None
    cursor = None
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        required_fields = ['user_id', 'amount', 'journal_id', 'quantity']
        for field in required_fields:
            if field not in data:
                return jsonify({"success": False, "error": f"Missing required field: {field}"}), 400

        user_id = data['user_id']
        journal_id = data['journal_id']
        quantity = int(data['quantity'])
        amount = float(data['amount'])
        
        if quantity <= 0:
            return jsonify({"success": False, "error": "Quantity must be positive"}), 400

        # Подключение к базе данных
        conn = db_pool.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Начинаем транзакцию
        cursor.execute("START TRANSACTION")
        
        # 1. Проверяем наличие товара с блокировкой строки
        cursor.execute("SELECT quantity, price FROM journals WHERE id = %s FOR UPDATE", (journal_id,))
        journal = cursor.fetchone()
        
        if not journal:
            conn.rollback()
            return jsonify({"success": False, "error": "Journal not found"}), 404
            
        available_quantity = journal['quantity']
        
        if available_quantity < quantity:
            conn.rollback()
            return jsonify({
                "success": False,
                "error": f"Not enough items in stock. Available: {available_quantity}, requested: {quantity}"
            }), 400
        
        # 2. Создаем платеж в платежной системе
        payment = Payment.create({
            "amount": {
                "value": f"{amount:.2f}",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/CocoCamBot"
            },
            "metadata": {
                "user_id": user_id,
                "journal_id": journal_id,
                "quantity": quantity,
                **{k: data.get(k, '') for k in ['fullname', 'city', 'postcode', 'phone', 'email', 'chat_id']}
            },
            "description": f"Оплата журнала ID {journal_id}"
        })
        
        # 3. Обновляем количество товара
        cursor.execute(
            "UPDATE journals SET quantity = quantity - %s WHERE id = %s",
            (quantity, journal_id)
        )
        
        # 4. Сохраняем информацию о платеже (используем существующую структуру таблицы)
        cursor.execute(
            """INSERT INTO payments 
            (payment_id, user_id, journal_id, amount, status) 
            VALUES (%s, %s, %s, %s, 'pending')""",
            (payment.id, user_id, journal_id, amount)
        )
        
        # Фиксируем транзакцию
        conn.commit()
        
        return jsonify({
            "success": True,
            "payment_url": payment.confirmation.confirmation_url,
            "payment_id": payment.id
        })

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Payment processing error: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
            

@app.route('/payment_webhook', methods=['POST'])
def payment_webhook():
    logger.info("Webhook received. Headers: %s", request.headers)
    logger.info("Raw body: %s", request.data.decode('utf-8') if request.data else 'Empty body')
    
    conn = None
    cursor = None
    
    try:
        event_json = request.json
        payment = event_json['object']
        payment_id = payment['id']
        status = payment['status']
        metadata = payment.get('metadata', {})
        
        # Проверяем наличие обязательных данных
        if not all(key in metadata for key in ['chat_id', 'journal_id', 'quantity']):
            logger.error("Missing required metadata fields")
            return jsonify({"error": "Missing metadata"}), 400

        conn = db_pool.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Start transaction
        cursor.execute("START TRANSACTION")
        
        # Get payment data with lock
        cursor.execute(
            "SELECT * FROM payments WHERE payment_id = %s FOR UPDATE",
            (payment_id,)
        )
        payment_data = cursor.fetchone()
        
        if not payment_data:
            conn.rollback()
            return jsonify({"status": "payment not found"}), 404
            
        if status == 'succeeded':
            # Complete the transaction - save order
            cursor.execute(
                """INSERT INTO orders (
                    tg_user_id, fullname, city, postcode, 
                    phone, email, product_id, quantity, 
                    amount, payment_id, status, currency
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'paid', 'RUB'
                )""",
                (
                    payment_data['user_id'],
                    metadata.get('fullname'),
                    metadata.get('city'),
                    metadata.get('postcode'),
                    metadata.get('phone'),
                    metadata.get('email'),
                    payment_data['journal_id'],
                    payment_data['quantity'],
                    payment_data['amount'],
                    payment_id
                )
            )
            
            cursor.execute(
                "UPDATE payments SET status = 'succeeded' WHERE payment_id = %s",
                (payment_id,)
            )
            
            # Обновляем количество журналов
            cursor.execute(
                "UPDATE journals SET quantity = quantity - %s WHERE id = %s",
                (payment_data['quantity'], payment_data['journal_id'])
            )
            
            # Send notification
            send_telegram_notification(
                chat_id=metadata['chat_id'],
                payment_id=payment_id,
                amount=payment_data['amount'],
                product_id=payment_data['journal_id'],
                customer_name=metadata.get('fullname'),
                delivery_city=metadata.get('city'),
                delivery_postcode=metadata.get('postcode')
            )
                
        elif status in ['canceled', 'failed']:
            # Return journals to stock
            cursor.execute(
                "UPDATE journals SET quantity = quantity + %s WHERE id = %s",
                (payment_data['quantity'], payment_data['journal_id'])
            )
            cursor.execute(
                "UPDATE payments SET status = %s WHERE payment_id = %s",
                (status, payment_id)
            )
            
        conn.commit()
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"Webhook error: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


def send_telegram_notification(chat_id, payment_id, amount, product_id, customer_name, delivery_city, delivery_postcode):
    """Отправляет уведомление о заказе в Telegram"""
    try:
        bot_token = os.getenv('BOT_TOKEN')
        if not bot_token:
            raise ValueError("BOT_TOKEN environment variable not set")
            
        message = f"""
        🛍️ Новый оплаченный заказ
        
        🔹 Номер платежа: {payment_id}
        🔹 Сумма: {amount:.2f} RUB
        🔹 Товар: #{product_id}
        
        Данные доставки:
        👤 ФИО: {customer_name}
        🏙️ Город: {delivery_city}
        📮 Индекс: {delivery_postcode}
        """
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        params = {
            'chat_id': int(chat_id),
            'text': message,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, json=params, timeout=10)
        response.raise_for_status()
        
        logger.info(f"Notification sent to chat {chat_id}. Response: {response.text}")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Telegram API request failed: {str(e)}")
    except Exception as e:
        logger.error(f"Error sending Telegram notification: {str(e)}", exc_info=True)
        raise
        
        




# def send_telegram_notification(chat_id, payment_id, amount, product_id, customer_name, delivery_city, delivery_postcode):
#     """Отправляет уведомление о заказе в Telegram"""
#     try:
#         message = f"""
#         🛍️ Новый оплаченный заказ
        
#         🔹 Номер платежа: {payment_id}
#         🔹 Сумма: {amount:.2f} RUB
#         🔹 Товар: #{product_id}
        
#         Данные доставки:
#         👤 ФИО: {customer_name}
#         🏙️ Город: {delivery_city}
#         📮 Индекс: {delivery_postcode}
#         """
        
#         # Реализация отправки через Telegram Bot API
#         bot_token = os.getenv('BOT_TOKEN')
#         url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
#         params = {
#             'chat_id': chat_id,
#             'text': message
#         }
        
#         response = requests.post(url, json=params)
#         response.raise_for_status()
        
#         logger.info(f"Notification sent to chat {chat_id}")
        
#     except Exception as e:
#         logger.error(f"Failed to send Telegram notification: {str(e)}")
        
        


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


@app.route('/debug/payment/<payment_ref>', methods=['GET'])
def debug_payment(payment_ref):
    try:
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT * FROM payments 
            WHERE return_id = %s OR payment_id LIKE %s""",
            (f"pay_{payment_ref}", f"%{payment_ref}%")
        )
        payment = cursor.fetchone()
        cursor.close()
        conn.close()
        
        return jsonify({
            "exists": bool(payment),
            "payment": payment
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    
    


if __name__ == '__main__':
    init_db()
    try:
        app.run(host='0.0.0.0', port=5005, debug=True)
    finally:
        if db_pool:
            db_pool.close()




# from flask import Flask, request, jsonify
# from yookassa import Configuration, Payment

# from mysql.connector import Error
# from dotenv import load_dotenv

# from aiohttp import web

# from aiomysql import create_pool

# from aiohttp_middlewares import cors_middleware

# from flask_cors import CORS

# import uuid
# import logging
# import mysql.connector
# import os


# load_dotenv()

# app = Flask(__name__)
# CORS(app)

# # Настройка ЮKassa
# Configuration.account_id = os.getenv('YOOKASSA_SHOP_ID')
# Configuration.secret_key = os.getenv('YOOKASSA_SECRET_KEY')



# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)


# app = web.Application(middlewares=[
#     cors_middleware(allow_all=True)  # Разрешаем все CORS-запросы
# ])


# async def init_db(app):
#     """Инициализация пула соединений с MySQL"""
#     try:
#         app['db_pool'] = await create_pool(
#             unix_socket='/Applications/MAMP/tmp/mysql/mysql.sock',
#             user='root',
#             password='root',
#             db='tg_bot',
#             port=8889,
#             minsize=1,
#             maxsize=5
#         )
#         logger.info("✅ Пул соединений с MySQL инициализирован")
#     except Exception as e:
#         logger.error(f"❌ Ошибка подключения к MySQL: {e}")
#         raise

# async def save_order(db_pool, order_data):
#     """Сохранение заказа в БД"""
#     async with db_pool.acquire() as conn:
#         async with conn.cursor() as cursor:
#             await cursor.execute('''
#                 INSERT INTO orders 
#                 (tg_user_id, tg_username, city, postcode, phone, email, 
#                  product_id, quantity, amount, payment_id, status, is_test)
#                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
#             ''', (
#                 order_data['user_id'],
#                 order_data.get('username'),
#                 order_data['city'],
#                 order_data['postcode'],
#                 order_data['phone'],
#                 order_data['email'],
#                 order_data['product_id'],
#                 order_data['quantity'],
#                 order_data['amount'],
#                 order_data['payment_id'],
#                 'pending',
#                 order_data.get('is_test', False)
#             ))
#             await conn.commit()

# async def update_order_status(db_pool, payment_id):
#     """Обновление статуса заказа"""
#     async with db_pool.acquire() as conn:
#         async with conn.cursor() as cursor:
#             await cursor.execute('''
#                 UPDATE orders 
#                 SET status = 'paid' 
#                 WHERE payment_id = %s
#             ''', (payment_id,))
#             await conn.commit()



# async def create_payment(request):
#     try:
#         data = await request.json()
        
#         # Тестовые данные вместо реального платежа
#         test_payment = {
#             "id": "test_payment_123",
#             "confirmation": {
#                 "confirmation_url": "https://example.com/success.html"
#             },
#             "test": True
#         }

#         return web.json_response({
#             "payment_id": test_payment["id"],
#             "confirmation_url": test_payment["confirmation"]["confirmation_url"],
#             "is_test": True
#         })
        
#     except Exception as e:
#         return web.json_response({"error": str(e)}, status=500)
    
    

# async def payment_webhook(request):
#     """Обработчик webhook от ЮKassa"""
#     try:
#         event_json = await request.json()
#         if event_json['event'] == 'payment.succeeded':
#             payment_id = event_json['object']['id']
#             await update_order_status(request.app['db_pool'], payment_id)
        
#         return web.Response(status=200)
#     except Exception as e:
#         logger.error(f"Ошибка в webhook: {e}")
#         return web.Response(status=400)

# async def init_app():
#     """Инициализация приложения"""
#     app = web.Application()
    
#     # Инициализация БД
#     app.on_startup.append(init_db)
    
#     # Маршруты
#     app.router.add_post('/create_payment', create_payment)
#     app.router.add_post('/payment_webhook', payment_webhook)
    
#     return app


# app.router.add_post('/create_payment', create_payment)


# if __name__ == '__main__':
#     web.run_app(init_app(), port=5005)