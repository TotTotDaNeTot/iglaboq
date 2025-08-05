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



@app.route('/create_payment', methods=['POST'])
def create_payment():
    try:
        data = request.json
        user_id = data['user_id']
        chat_id = data.get('chat_id', user_id)
        amount = float(data['amount'])
        journal_id = data.get('journal_id')

        payment = Payment.create({
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/CocoCamBot"  # Просто возвращаем в бота
            },
            "metadata": {
                "user_id": user_id,
                "chat_id": chat_id,
                "journal_id": journal_id
            }
        })

        # Сохраняем в БД
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO payments 
            (payment_id, user_id, chat_id, amount, status, journal_id) 
            VALUES (%s, %s, %s, %s, %s, %s)""",
            (payment.id, user_id, chat_id, amount, 'pending', journal_id)
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
        logger.info(f"Raw webhook data: {request.data}")
        
        event_json = request.json
        payment = event_json['object']
        logger.info(f"Webhook received for payment: {payment['id']}, status: {payment['status']}")
        
        # Обрабатываем оба статуса - waiting_for_capture и succeeded
        if payment['status'] in ['waiting_for_capture', 'succeeded']:
            # Для waiting_for_capture - подтверждаем платеж автоматически
            if payment['status'] == 'waiting_for_capture':
                from yookassa import Payment
                Payment.capture(payment['id'])
                logger.info(f"Payment {payment['id']} captured automatically")
            
            # Обновляем статус в БД
            db_status = 'succeeded' if payment['status'] == 'succeeded' else 'pending_capture'
            rows_updated = update_payment_status(payment['id'], db_status)
            logger.info(f"Database updated rows: {rows_updated}")
            
            # Отправляем уведомление только для succeeded
            if payment['status'] == 'succeeded':
                metadata = payment.get('metadata', {})
                chat_id = metadata.get('chat_id')
                if chat_id:
                    send_telegram_notification(
                        chat_id,
                        payment['id'],
                        payment['amount']['value']
                    )
                    
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    
    

def capture_payment(payment_id: str):
    """Автоматически подтверждает платеж в ЮKassa"""
    try:
        response = Payment.capture(payment_id)
        logger.info(f"Payment {payment_id} captured, new status: {response.status}")
        return response
    except Exception as e:
        logger.error(f"Failed to capture payment {payment_id}: {str(e)}")
        raise
    
    
    
    
@app.route('/check_and_capture/<payment_id>', methods=['GET'])
def check_and_capture(payment_id: str):
    """Проверяет и подтверждает платеж вручную"""
    try:
        from yookassa import Payment
        payment = Payment.find_one(payment_id)
        
        if payment.status == 'waiting_for_capture':
            # Подтверждаем платеж
            captured_payment = capture_payment(payment_id)
            update_payment_status(payment_id, 'succeeded')
            return jsonify({
                "original_status": payment.status,
                "new_status": captured_payment.status,
                "captured": True
            })
        else:
            update_payment_status(payment_id, payment.status)
            return jsonify({"status": payment.status})
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
    
    

def send_direct_notification(chat_id: int, payment_id: str, amount: str):
    """Функция для прямой отправки уведомления"""
    bot_token = os.getenv('BOT_TOKEN')
    message = (
        f"✅ Платеж успешен!\n"
        f"ID: {payment_id}\n"
        f"Сумма: {amount} RUB\n"
        "Товар будет отправлен в течение 3 рабочих дней."
    )
    
    requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
    )



def send_telegram_notification(chat_id: int, payment_id: str, amount: str):
    """Отправляет уведомление через Telegram API"""
    bot_token = os.getenv('BOT_TOKEN')
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": (
            f"✅ Платеж успешен!\n"
            f"Сумма: {amount} RUB\n"
            f"Номер: {payment_id}\n"
            "Трек-номер будет отправлен в течение 24 часов"
        ),
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info(f"Telegram notification sent to {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")
        
        


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