from minio import Minio
from minio.error import S3Error
from config import Config

import json
import os 
import logging


logger = logging.getLogger(__name__)




class MinioService:
    def __init__(self):
        print(f"🔗 Connecting to MinIO at: {Config.MINIO_ENDPOINT}")
        print(f"🔑 Using access key: {Config.MINIO_ACCESS_KEY}")
        
        self.client = Minio(
            Config.MINIO_ENDPOINT,
            access_key=Config.MINIO_ACCESS_KEY,
            secret_key=Config.MINIO_SECRET_KEY,
            secure=Config.MINIO_SECURE
        )
        
        self.bucket_name = Config.MINIO_BUCKET 
        
        # Тест подключения
        try:
            buckets = self.client.list_buckets()
            print("✅ MinIO connection successful!")
            print(f"📦 Available buckets: {[b.name for b in buckets]}")
        except Exception as e:
            print(f"❌ MinIO connection failed: {e}")
            print("ℹ️  Check your credentials in config.py")
            print(f"ℹ️  MinIO URL: http://{Config.MINIO_ENDPOINT}")
            raise
        

        self.set_bucket_public()
        
        
    
    def set_bucket_public(self):
        """Делает bucket полностью публичным"""
        try:
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": "*"},
                        "Action": ["s3:GetObject", "s3:ListBucket"],
                        "Resource": [
                            f"arn:aws:s3:::{self.bucket_name}",
                            f"arn:aws:s3:::{self.bucket_name}/*"
                        ]
                    }
                ]
            }
            
            self.client.set_bucket_policy(self.bucket_name, json.dumps(policy))
            print(f"✅ Bucket '{self.bucket_name}' set to PUBLIC")
            return True
            
        except Exception as e:
            print(f"❌ Error making bucket public: {e}")
            return False
    
    def upload_image(self, journal_id: str, file_contents: bytes, filename: str):
        """Загружает изображение в MinIO с уникальным именем"""
        
        print(f"📤 Uploading image: journal_id={journal_id}, filename={filename}, size={len(file_contents)} bytes")
        
        import uuid
        import datetime
        import io 
        
        file_extension = os.path.splitext(filename)[1].lower()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{uuid.uuid4().hex[:8]}{file_extension}"
        
        object_name = f"journal_{journal_id}/{unique_filename}"
        
        try:
            self.client.put_object(
                self.bucket_name,
                object_name,
                io.BytesIO(file_contents),  # ← ПЕРЕДАЕМ bytes
                len(file_contents),
                content_type=self._get_content_type(filename)
            )
            
            public_url = f"https://dismally-familiar-sharksucker.cloudpub.ru/minio_proxy/{self.bucket_name}/{object_name}"
            
            print(f"✅ Uploaded image: {public_url}")
            return public_url, unique_filename
            
        except S3Error as e:
            print(f"❌ Error uploading image: {e}")
            return None, None
        
        
        
    def upload_bot_image(self, journal_id: str, file_contents: bytes, filename: str):
        """Загружает изображение для бота в отдельный bucket"""
        print(f"📤 Uploading bot image: journal_id={journal_id}, filename={filename}, size={len(file_contents)} bytes")
        
        import uuid
        import datetime
        import io 
        
        file_extension = os.path.splitext(filename)[1].lower()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{uuid.uuid4().hex[:8]}{file_extension}"
        
        object_name = f"journal_{journal_id}/{unique_filename}"
        
        try:
            self.client.put_object(
                "journals-bot",  # ОТДЕЛЬНЫЙ BUCKET ДЛЯ БОТА
                object_name,
                io.BytesIO(file_contents),
                len(file_contents),
                content_type=self._get_content_type(filename)
            )
            
            public_url = f"https://dismally-familiar-sharksucker.cloudpub.ru/fast_image_bot/{object_name}"
            
            print(f"✅ Uploaded bot image: {public_url}")
            return public_url, unique_filename
            
        except S3Error as e:
            print(f"❌ Error uploading bot image: {e}")
            return None, None
        
        
    
    
    def delete_image(self, journal_id, filename):
        """Удаляет изображение из MinIO"""
        object_name = f"journal_{journal_id}/{filename}"
        
        try:
            self.client.remove_object(self.bucket_name, object_name) 
            print(f"✅ Deleted image: {object_name}")
            return True
        except S3Error as e:
            print(f"❌ Error deleting image: {e}")
            return False
        
        
    
    def set_bucket_public(self):
        """Устанавливает публичный доступ к bucket для чтения"""
        try:
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": "*"},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{self.bucket_name}/*"]
                    }
                ]
            }
            
            self.client.set_bucket_policy(self.bucket_name, json.dumps(policy))
            print(f"✅ Bucket '{self.bucket_name}' set to public read access")
            return True
            
        except S3Error as e:
            print(f"❌ Error setting bucket policy: {e}")
            return False
    
    
    
    
    def delete_bot_image(self, object_path):
        """Удаляет изображение бота"""
        try:
            self.client.remove_object("journals-bot", object_path)
            print(f"✅ Deleted bot image: {object_path}")
            return True
        except S3Error as e:
            print(f"❌ Error deleting bot image: {e}")
            return False
        
        
    def _get_content_type(self, filename: str):
        """Определяет content type по расширению файла"""
        if filename.lower().endswith('.png'):
            return 'image/png'
        elif filename.lower().endswith(('.jpg', '.jpeg')):
            return 'image/jpeg'
        elif filename.lower().endswith('.gif'):
            return 'image/gif'
        else:
            return 'application/octet-stream'
    

# Создаем глобальный экземпляр
minio_service = MinioService()