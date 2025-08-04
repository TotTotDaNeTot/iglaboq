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
import requests

from gunicorn.glogging import Logger
from yookassa import Configuration, Payment
from aiomysql import create_pool

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
        
        # Create payment in YooKassa
        payment = Payment.create({
            "amount": {
                "value": f"{amount:.2f}",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://worldly-natural-glassfish.cloudpub.ru/payment_success?user_id={user_id}"
            },
            "capture": True,
            "description": f"Payment for journal {data.get('journal_id', '')}",
            "metadata": {
                "user_id": user_id,
                "journal_id": data.get('journal_id'),
                "amount": amount
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

@app.route('/payment_success')
def payment_success():
    user_id = request.args.get('user_id')
    
    # Return HTML page that will close the WebApp
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Payment Successful</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body {{ 
                font-family: Arial, sans-serif; 
                text-align: center; 
                padding: 40px 20px;
                background-color: #f5f5f5;
            }}
            .success-container {{
                max-width: 500px;
                margin: 0 auto;
                padding: 30px;
                background: white;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .success-icon {{
                color: #4CAF50;
                font-size: 60px;
                margin-bottom: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="success-container">
            <div class="success-icon">✓</div>
            <h2>Payment Successful</h2>
            <p>Thank you for your purchase!</p>
            <p>You will receive a confirmation shortly.</p>
        </div>
        <script>
            // Close WebApp after 3 seconds
            setTimeout(() => {{
                if (window.Telegram && Telegram.WebApp && Telegram.WebApp.close) {{
                    Telegram.WebApp.close();
                }}
            }}, 3000);
            
            // Notify bot about successful payment
            if (window.Telegram && Telegram.WebApp && Telegram.WebApp.sendData) {{
                Telegram.WebApp.sendData(JSON.stringify({{
                    type: 'payment_success',
                    user_id: '{user_id}'
                }}));
            }}
        </script>
    </body>
    </html>
    """

@app.route('/payment_webhook', methods=['POST'])
def payment_webhook():
    try:
        event_json = request.json
        payment = event_json['object']
        
        if payment['status'] == 'succeeded':
            user_id = payment['metadata']['user_id']
            payment_id = payment['id']
            amount = payment['amount']['value']
            
            # Update database
            conn = db_pool.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE payments SET status = 'succeeded' WHERE payment_id = %s",
                (payment_id,)
            )
            conn.commit()
            cursor.close()
            conn.close()
            
            # Send confirmation message
            send_telegram_message(
                user_id,
                f"✅ Payment successful!\n"
                f"Amount: {amount} RUB\n"
                f"Payment ID: {payment_id}\n"
                f"Tracking number will be sent within 24 hours"
            )
            
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

def send_telegram_message(user_id, text):
    bot_token = os.getenv('BOT_TOKEN')
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": user_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
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