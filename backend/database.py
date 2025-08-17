import aiomysql
from typing import Optional, List, Dict, Any
import logging
import os
import asyncio

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties

from dotenv import load_dotenv
load_dotenv()


# BOT_TOKEN = os.getenv('BOT_TOKEN')
# if not BOT_TOKEN:
#     raise ValueError("Не указан BOT_TOKEN в переменных окружения")

# bot = Bot(
#     token=BOT_TOKEN,
#     default=DefaultBotProperties(parse_mode=ParseMode.HTML)
# )



class Database:
    def __init__(self):
        self.pool: Optional[aiomysql.Pool] = None
        self.logger = logging.getLogger(__name__)

    async def connect(self, **kwargs):
        try:
            self.pool = await aiomysql.create_pool(
                unix_socket='/Applications/MAMP/tmp/mysql/mysql.sock',
                user='root',
                password='root',
                db='tg_bot',
                port=8889,
                autocommit=True,
                minsize=1,
                maxsize=5
            )
            self.logger.info("✅ Пул соединений с БД создан")
        except Exception as e:
            self.logger.error(f"❌ Ошибка подключения: {e}")
            raise
        
    
    async def save_order(
        self,
        tg_user_id: int,
        tg_username: str,
        city: str,
        postcode: str,
        phone: str,
        email: str,
        product_id: str,
        quantity: int,
        amount: float,
        payment_id: str,
        status: str = 'pending',
        is_test: bool = False
    ):
        """Сохранение заказа в БД"""
        await self.execute(
            """
            INSERT INTO orders 
            (tg_user_id, tg_username, city, postcode, phone, email, 
            product_id, quantity, amount, payment_id, status, is_test)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (tg_user_id, tg_username, city, postcode, phone, email,
            product_id, quantity, amount, payment_id, status, int(is_test))
        )    
        
    async def add_journal(
        self,
        title: str,
        description: str,
        price: float,
        year: int,
        photo_path: str = None,
        photo_url: str = None
    ):
        """Добавляет журнал в базу данных"""
        await self.execute(
            "INSERT INTO journals (title, description, price, year, photo_path, photo_url) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (title, description, price, year, photo_path, photo_url)
        )
        
        

    async def get_all_journals(self) -> List[Dict[str, Any]]:
        """Получает все журналы из БД"""
        return await self.fetch_all("""
            SELECT id, title, description, price, year, photo_path, photo_url 
            FROM journals 
            ORDER BY year DESC
        """)
        
        

    async def get_journal_by_id(self, journal_id: int) -> Optional[Dict[str, Any]]:
        """Получает конкретный журнал по ID"""
        return await self.fetch_one("""
            SELECT id, title, description, price, year, photo_path, photo_url, quantity
            FROM journals 
            WHERE id = %s
        """, (journal_id,))
        
    
    
    async def update_order_status(self, order_id: str, status: str, payment_id: str = None):
        """Обновляет статус заказа"""
        query = """
            UPDATE orders 
            SET status = %s, 
                payment_id = COALESCE(%s, payment_id)
            WHERE order_id = %s
        """
        await self.execute(query, (status, payment_id, order_id))



    async def get_order_by_id(self, order_id: str) -> dict:
        """Получает заказ по ID"""
        return await self.fetch_one("""
            SELECT * FROM orders 
            WHERE order_id = %s
        """, (order_id,))
        
        
        
    ######### PAYMENTS ##########    
        
    async def create_payment(self, payment_id: str, user_id: int, amount: float, status: str = 'pending') -> bool:
        """Создает запись о платеже в БД"""
        try:
            await self.execute(
                """
                INSERT INTO payments (payment_id, user_id, amount, status)
                VALUES (%s, %s, %s, %s)
                """,
                (payment_id, user_id, amount, status)
            )
            return True
        except Exception as e:
            self.logger.error(f"Error creating payment: {e}")
            return False

    async def update_payment_status(self, payment_id: str, status: str) -> bool:
        """Обновляет статус платежа"""
        try:
            await self.execute(
                "UPDATE payments SET status = %s WHERE payment_id = %s",
                (status, payment_id)
            )
            return True
        except Exception as e:
            self.logger.error(f"Error updating payment status: {e}")
            return False

    async def get_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Получает информацию о платеже"""
        try:
            return await self.fetch_one(
                "SELECT * FROM payments WHERE payment_id = %s",
                (payment_id,)
            )
        except Exception as e:
            self.logger.error(f"Error getting payment: {e}")
            return None

    async def get_user_payments(self, user_id: int) -> List[Dict[str, Any]]:
        """Получает все платежи пользователя"""
        try:
            return await self.fetch_all(
                "SELECT * FROM payments WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,)
            )
        except Exception as e:
            self.logger.error(f"Error getting user payments: {e}")
            return []
        
        
        
    ##### ADMIN #######

    async def create_admin(self, username: str, password_hash: str, is_staff: bool = False) -> bool:
        """Создает администратора"""
        try:
            await self.execute(
                "INSERT INTO admins (username, password_hash, is_staff) VALUES (%s, %s, %s)",
                (username, password_hash, is_staff)
            )
            return True
        except Exception as e:
            self.logger.error(f"Error creating admin: {e}")
            return False


    async def get_admin_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Получает администратора по username"""
        try:
            return await self.fetch_one(
                "SELECT * FROM admins WHERE username = %s",
                (username,)
            )
        except Exception as e:
            self.logger.error(f"Error getting admin: {e}")
            return None


    async def verify_admin(self, username: str, password: str) -> bool:
        """Проверяет логин/пароль администратора"""
        from werkzeug.security import check_password_hash
        
        admin = await self.get_admin_by_username(username)
        if not admin:
            return False
        
        return check_password_hash(admin['password_hash'], password)
    
    
    

    async def execute(self, query: str, args=None):
        if not self.pool:
            raise RuntimeError("Пула соединений не существует")
        
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, args or ())
                return cur

    async def fetch_all(self, query: str, args=None) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, args or ())
                return await cur.fetchall()

    async def fetch_one(self, query: str, args=None) -> Dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, args or ())
                return await cur.fetchone()
    
    def sync_fetch_one(self, query: str, args=None):
        """Синхронная версия fetch_one"""
        
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.fetch_one(query, args))
        finally:
            loop.close()

    async def close(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()

# Глобальный экземпляр
db = Database()