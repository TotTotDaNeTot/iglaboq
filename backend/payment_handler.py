from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import uuid
import sys
from gunicorn.glogging import Logger


app = Flask(__name__)
CORS(app)  # Разрешаем все CORS-запросы

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



@app.route('/health')
def health_check():
    return jsonify({"status": "ok", "version": "1.0"}), 200

@app.route('/create_payment', methods=['POST'])
def create_payment():
    try:
        data = request.json
        logger.info(f"Received payment request: {data}")
        
        # Тестовый ответ
        return jsonify({
            "payment_id": "test_123",
            "confirmation_url": "https://example.com/success",
            "is_test": True
        }), 200
        
    except Exception as e:
        logger.error(f"Payment error: {str(e)}")
        return jsonify({"error": "Payment processing failed"}), 500

# Важно: убираем блок с gunicorn.app.wsgiapp
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005)




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