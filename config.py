import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

class Config:
    # MinIO configuration
    MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT')
    MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY')
    MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY')
    MINIO_SECURE = os.getenv('MINIO_SECURE', 'False').lower() == 'true'
    MINIO_BUCKET = os.getenv('MINIO_BUCKET')
    MINIO_PUBLIC_URL = os.getenv('MINIO_PUBLIC_URL')
    
    # Database configuration
    DB_HOST = os.getenv('DB_HOST')
    DB_USER = os.getenv('DB_USER')
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    DB_NAME = os.getenv('DB_NAME')
    DB_PORT = int(os.getenv('DB_PORT'))
    
    # Flask configuration
    ADMIN_SECRET_KEY = os.getenv('ADMIN_SECRET_KEY')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # Email configuration
    EMAIL_HOST = os.getenv('EMAIL_HOST')
    EMAIL_PORT = int(os.getenv('EMAIL_PORT'))
    EMAIL_USER = os.getenv('EMAIL_USER')
    EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
    
    # @property
    # def db_config(self):
    #     return {
    #         'host': self.DB_HOST,
    #         'user': self.DB_USER,
    #         'password': self.DB_PASSWORD,
    #         'db': self.DB_NAME,
    #         'port': self.DB_PORT,
    #         'autocommit': False
    #     }

config = Config()