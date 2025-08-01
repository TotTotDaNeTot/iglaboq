import aiomysql
from typing import Optional, List, Dict, Any
import logging




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
            SELECT id, title, description, price, year, photo_path, photo_url
            FROM journals 
            WHERE id = %s
        """, (journal_id,))
        
        

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

    async def close(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()

# Глобальный экземпляр
db = Database()