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

from gunicorn.glogging import Logger
from yookassa import Configuration, Payment
from aiomysql import create_pool
from aiogram.fsm.storage.memory import MemoryStorage

from database import db 

import mysql.connector
from mysql.connector import pooling


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



@app.route('/create_payment', methods=['POST'])
def create_payment():
    try:
        data = request.json
        amount = float(data['amount'])
        user_id = data.get('user_id')
        chat_id = data.get('chat_id')  # Добавьте chat_id в данные с фронтенда

        # Для мобильных и десктопных клиентов разные return_url
        return_url = (
            f"https://web.telegram.org/k/#{chat_id}"
            if not data.get('is_mobile', False)
            else f"https://t.me/CocoCamBot?start=payment_success_{user_id}"
        )

        payment = Payment.create({
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "confirmation": {
                "type": "redirect",
                "return_url": return_url
            },
            "metadata": {
                "user_id": user_id,
                "chat_id": chat_id,
                "journal_id": data.get('journal_id')
            }
        })

        # Save to database
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO payments (payment_id, user_id, amount, status) VALUES (%s, %s, %s, %s)",
            (payment.id, user_id, amount, 'pending')
        )
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "payment_url": payment.confirmation.confirmation_url,
            "payment_id": payment.id
        })

    except Exception as e:
        logger.error(f"Payment creation failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    
    

@app.route('/payment_webhook', methods=['POST'])
def payment_webhook():
    try:
        event_json = request.json
        payment = event_json['object']
        
        if payment['status'] == 'succeeded':
            # Извлекаем данные из платежа
            metadata = payment.get('metadata', {})
            user_id = metadata.get('user_id')
            chat_id = metadata.get('chat_id')
            payment_id = payment['id']
            amount = payment['amount']['value']
            
            # Обновляем статус в базе данных
            update_payment_status(payment_id, 'succeeded')
            
            # Отправляем сообщение через JS (WebApp.sendData)
            # Дополнительно отправляем через бота для надежности
            payment_message = (
                f"✅ Платеж успешен!\n"
                f"Сумма: {amount} RUB\n"
                f"Номер: {payment_id}\n"
                f"Трек-номер будет отправлен в течение 24 часов"
            )
            
            # Отправляем в оба места (и в чат, и через WebApp)
            send_telegram_message(chat_id, payment_message)
            
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

def update_payment_status(payment_id: str, status: str):
    """Обновляет статус платежа в базе данных"""
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE payments SET status = %s WHERE payment_id = %s",
            (status, payment_id)
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Database update error: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



@dp.message(WebAppData)
async def handle_web_app_data(message: types.Message):
    """Обработчик данных из WebApp"""
    try:
        data = json.loads(message.web_app_data.data)
        
        if data.get('type') == 'payment_success':
            # Логируем полученные данные
            logger.info(f"Received payment success: {data}")
            
            # Можно добавить дополнительную обработку,
            # но основное сообщение уже отправлено из payment_webhook
            pass
            
    except json.JSONDecodeError:
        logger.error("Invalid JSON data from WebApp")
    except Exception as e:
        logger.error(f"WebApp data processing error: {e}")

def send_telegram_message(chat_id: int, text: str) -> bool:
    """Отправляет сообщение в Telegram чат"""
    bot_token = os.getenv('BOT_TOKEN')
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Telegram message sending failed: {e}")
        return False



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