from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties

from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
import logging
import uuid
import sys
import os
from gunicorn.glogging import Logger
from yookassa import Configuration, Payment
from aiomysql import create_pool

from backend.database import db 

import urllib.parse

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


# Конфигурация MySQL
async def get_db():
    return await create_pool(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        db=os.getenv('DB_NAME'),
        port=int(os.getenv('DB_PORT')))
    
        
@app.route('/create_payment', methods=['POST'])
async def create_payment():
    try:
        data = request.json
        
        # Валидация данных
        required_fields = ['user_id', 'journal_id', 'amount', 'quantity', 
                         'city', 'postcode', 'phone', 'email']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # Сохраняем заказ в БД перед оплатой
        order_id = str(uuid.uuid4())
        db_pool = await get_db()
        
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('''
                    INSERT INTO orders 
                    (order_id, tg_user_id, product_id, quantity, amount, 
                     city, postcode, phone, email, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ''', (
                    order_id,
                    data['user_id'],
                    data['journal_id'],
                    data['quantity'],
                    float(data['amount']),
                    data['city'],
                    data['postcode'],
                    data['phone'],
                    data['email'],
                    'pending'
                ))
                await conn.commit()

        # Получаем название журнала из метаданных (если передано)
        journal_title = data.get('metadata', {}).get('journal_title', data['journal_id'])

        # Создаем платеж в ЮKассе
        payment = Payment.create({
            "amount": {
                "value": f"{float(data['amount']):.2f}",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/CocoCamBot?start=payment_{order_id}"
            },
            "capture": True,
            "description": f"Журнал '{journal_title}' (кол-во: {data['quantity']})",
            "metadata": {
                "order_id": order_id,
                "user_id": data['user_id'],
                "telegram_chat_id": data['user_id'],  # Для вебхука
                "journal_id": data['journal_id'],
                "quantity": data['quantity']
            },
            "receipt": {
                "customer": {
                    "email": data['email']
                },
                "items": [{
                    "description": f"Журнал '{journal_title}'",
                    "quantity": str(data['quantity']),
                    "amount": {
                        "value": f"{float(data['amount'])/float(data['quantity']):.2f}",
                        "currency": "RUB"
                    },
                    "vat_code": "1",
                    "payment_mode": "full_prepayment",
                    "payment_subject": "commodity"
                }]
            }
        })

        # Обновляем order_id в БД с payment_id
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('''
                    UPDATE orders SET payment_id = %s 
                    WHERE order_id = %s
                ''', (payment.id, order_id))
                await conn.commit()

        return jsonify({
            "success": True,
            "payment_id": payment.id,
            "order_id": order_id,
            "confirmation_url": payment.confirmation.confirmation_url
        })

    except Exception as e:
        logger.error(f"Payment creation error: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Ошибка при создании платежа",
            "details": str(e)
        }), 500



@app.route('/payment_webhook', methods=['POST'])
async def payment_webhook():
    try:
        data = request.json
        if data['event'] == 'payment.succeeded':
            order_id = data['object']['metadata']['order_id']
            
            # Обновляем статус в БД
            await db.update_order_status(
                order_id=order_id,
                status='paid',
                payment_id=data['object']['id']
            )
            
            # Получаем chat_id из метаданных (добавьте его при создании платежа)
            chat_id = data['object']['metadata'].get('telegram_chat_id')
            if chat_id:
                order = await db.get_order_by_id(order_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ Платеж подтвержден!\nЗаказ №{order_id}\nСумма: {order['amount']}₽"
                )
            
        return jsonify({"status": "ok"}), 200
    
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500
    
  
  
    
@app.route('/payment_success')
def payment_success():
    # Обработка успешного платежа (для вебхуков)
    return redirect("https://t.me/CocoCamBot")
    

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005, debug=True)




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