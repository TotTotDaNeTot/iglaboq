from flask import Flask
from flask_cors import CORS
from database import db

import asyncio
import logging
import os



# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем глобальный event loop
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('ADMIN_SECRET_KEY')
CORS(app, resources={r"/*": {"origins": "*"}})



# Инициализация базы данных
try:
    loop.run_until_complete(db.connect())
    test = loop.run_until_complete(db.fetch_one("SELECT 1 AS test"))
    print("✅ Database connection successful:", test)
except Exception as e:
    print(f"❌ Database connection failed: {e}")
    exit(1)



# Глобальная функция run_async
def run_async(coro):
    """Синхронная обертка для асинхронных функций"""
    return loop.run_until_complete(coro)


# Добавляем run_async в контекст приложения
app.run_async = run_async

# Импортируем и регистрируем blueprint'ы
from api.minio_routes import minio_bp
from api.journal_routes import journal_bp
from api.bot_routes import bot_bp

app.register_blueprint(minio_bp)
app.register_blueprint(journal_bp)
app.register_blueprint(bot_bp)



@app.route('/')
def home():
    return "API Server is running"



if __name__ == '__main__':
    try:
        print("🟢 Starting server on http://localhost:5007")
        app.run(host='0.0.0.0', port=5007, debug=True)
    except Exception as e:
        print(f"❌ Server startup failed: {e}")
    finally:
        # Закрытие соединений при завершении
        try:
            loop.run_until_complete(db.close())
            print("✅ Database connection closed")
        except Exception as e:
            print(f"❌ Error closing database: {e}")
            
            