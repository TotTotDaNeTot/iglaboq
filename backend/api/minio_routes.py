from flask import Blueprint, request, jsonify, Response, current_app, send_file

from datetime import timedelta

from utils.minio_client import minio_client

from database import db

import logging
import requests
import hashlib
import os



# Создаем Blueprint для MinIO роутов
minio_bp = Blueprint('minio', __name__)

logger = logging.getLogger(__name__)



# Папка для кэша
CACHE_DIR = "/tmp/minio_cache"
os.makedirs(CACHE_DIR, exist_ok=True)




def run_async(coro):
    """Используем глобальную функцию run_async из app"""
    return current_app.run_async(coro)



@minio_bp.route('/minio_proxy/<path:minio_path>')
def minio_proxy(minio_path):
    """ПРОСТОЙ HTTP ПРОКСИ БЕЗ MINIO SDK"""
    try:
        print(f"🔍 Minio proxy requested: {minio_path}")
        
        # ПРЯМОЙ ДОСТУП К MINIO UI (порт 9001)
        minio_url = f'http://localhost:9001/{minio_path}'
        
        # Basic auth 
        auth = (os.getenv('MINIO_ACCESS_KEY'), os.getenv('MINIO_SECRET_KEY'))
        
        response = requests.get(minio_url, auth=auth, timeout=10, stream=True)
        
        print(f"📡 Minio response status: {response.status_code}")
        
        if response.status_code == 200:
            # Определяем content type по расширению файла
            if minio_path.lower().endswith('.png'):
                content_type = 'image/png'
            elif minio_path.lower().endswith(('.jpg', '.jpeg')):
                content_type = 'image/jpeg'
            elif minio_path.lower().endswith('.gif'):
                content_type = 'image/gif'
            else:
                content_type = 'application/octet-stream'
            
            return Response(
                response.iter_content(chunk_size=8192),
                content_type=content_type,
                headers={
                    'Cache-Control': 'public, max-age=86400',
                    'Access-Control-Allow-Origin': '*'
                }
            )
        else:
            print(f"❌ Minio error: {response.text}")
            return jsonify({"error": "Image not found", "status": response.status_code}), 404
            
    except Exception as e:
        print(f"💥 Minio proxy error: {str(e)}")
        return jsonify({"error": "Server error"}), 500
    
    
    
@minio_bp.route('/debug_minio')
def debug_minio():
    """ПРОСТАЯ ПРОВЕРКА MINIO"""
    try:
        # Прямой запрос к Minio UI
        response = requests.get(
            'http://localhost:9001/journals/',
            auth = (os.getenv('MINIO_ACCESS_KEY'), os.getenv('MINIO_SECRET_KEY')),
            timeout=5
        )
        
        return f"""
        <h2>Minio Debug</h2>
        <p><b>Status:</b> {response.status_code}</p>
        <p><b>Content:</b></p>
        <pre>{response.text}</pre>
        """
        
    except Exception as e:
        return f"<h2>Error</h2><pre>{str(e)}</pre>"
    
    

@minio_bp.route('/get_presigned_url')
def get_presigned_url():
    """Генерирует presigned URL для изображения"""
    try:
        path = request.args.get('path')
        if not path:
            return jsonify({"error": "Path parameter required"}), 400
        
        # Убираем префикс если есть
        if path.startswith('journals/'):
            object_path = path[len('journals/'):]
        else:
            object_path = path
        
        # Генерируем presigned URL
        presigned_url = minio_client.presigned_get_object(
            "journals",
            object_path,
            expires=timedelta(hours=24)
        )
        
        return jsonify({"presigned_url": presigned_url})
        
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        return jsonify({"error": str(e)}), 500
    
    
    
@minio_bp.route('/image_proxy/<path:image_path>')
def image_proxy(image_path):
    """Прокси для изображений с Minio (решает проблему CORS)"""
    try:
        print(f"🔍 Image proxy requested: {image_path}")
        
        # Генерируем presigned URL напрямую к Minio
        presigned_url = minio_client.presigned_get_object(
            "journals",  # bucket name
            image_path,  # полный путь к файлу
            expires=timedelta(hours=24)
        )
        
        print(f"📡 Fetching from Minio: {presigned_url}")
        
        # Загружаем изображение через requests
        response = requests.get(presigned_url, timeout=10, stream=True)
        
        print(f"✅ Minio response: {response.status_code}")
        
        if response.status_code == 200:
            # Определяем content type
            content_type = 'image/jpeg'
            if image_path.lower().endswith('.png'):
                content_type = 'image/png'
            elif image_path.lower().endswith('.gif'):
                content_type = 'image/gif'
            
            return Response(
                response.iter_content(chunk_size=8192),
                content_type=content_type,
                headers={
                    'Access-Control-Allow-Origin': '*',
                    'Cache-Control': 'public, max-age=86400'
                }
            )
        else:
            return jsonify({"error": "Image not found in Minio"}), 404
            
    except Exception as e:
        print(f"💥 Image proxy error: {e}")
        return jsonify({"error": str(e)}), 500
    
    
    
@minio_bp.route('/fast_image/<path:image_path>')
def fast_image(image_path):
    """Ускоренный прокси для изображений журналов"""
    try:
        print(f"🚀 Fast image requested: {image_path}")
        
        # Генерируем presigned URL
        presigned_url = minio_client.presigned_get_object(
            "journals", 
            image_path, 
            expires=timedelta(hours=24) 
        )
        
        # Скачиваем изображение с увеличенным таймаутом
        response = requests.get(presigned_url, timeout=10, stream=True)
        
        if response.status_code == 200:
            # ОПТИМИЗАЦИЯ: используем content-type из headers MinIO (как в fast_image_bot)
            content_type = response.headers.get('Content-Type', 'image/jpeg')
            
            # Fallback по расширению только если не определился
            if not content_type.startswith('image/'):
                if image_path.lower().endswith('.png'):
                    content_type = 'image/png'
                elif image_path.lower().endswith('.gif'):
                    content_type = 'image/gif'
                else:
                    content_type = 'image/jpeg'
            
            # Увеличиваем chunk size для большей скорости
            return Response(
                response.iter_content(chunk_size=32768),  # 32KB вместо 8KB
                content_type=content_type,
                headers={
                    'Cache-Control': 'public, max-age=86400',
                    'Access-Control-Allow-Origin': '*',
                    'CDN-Cache-Control': 'public, max-age=86400'
                }
            )
        else:
            return jsonify({"error": "Image not found"}), 404
            
    except requests.exceptions.Timeout:
        print(f"⏰ Timeout fetching image: {image_path}")
        return jsonify({"error": "Timeout"}), 504
    except Exception as e:
        print(f"💥 Fast image error: {e}")
        return jsonify({"error": str(e)}), 500   



@minio_bp.route('/fast_image_bot/<path:image_path>')
def fast_image_bot(image_path):
    """Супер-быстрый прокси для бота"""
    try:
        print(f"🚀 Fast BOT image requested: {image_path}")
        
        # Генерируем presigned URL
        presigned_url = minio_client.presigned_get_object(
            "journals-bot", 
            image_path, 
            expires=timedelta(hours=24)
        )
        
        # Скачиваем изображение
        response = requests.get(presigned_url, timeout=3, stream=True)
        
        print(f"📡 Minio response status: {response.status_code}")
        
        if response.status_code == 200:
            # Определяем content type
            content_type = response.headers.get('Content-Type', 'image/jpeg')
            if not content_type.startswith('image/'):
                if image_path.lower().endswith('.png'):
                    content_type = 'image/png'
                elif image_path.lower().endswith(('.jpg', '.jpeg')):
                    content_type = 'image/jpeg'
                elif image_path.lower().endswith('.gif'):
                    content_type = 'image/gif'
                else:
                    content_type = 'image/jpeg'
            
            # Возвращаем с агрессивным кэшированием
            return Response(
                response.iter_content(chunk_size=8192),
                content_type=content_type,
                headers={
                    'Cache-Control': 'public, max-age=86400',
                    'Access-Control-Allow-Origin': '*',
                    'CDN-Cache-Control': 'public, max-age=86400'
                }
            )
        else:
            print(f"❌ Minio error: {response.text}")
            return jsonify({"error": "Image not found"}), 404
            
    except Exception as e:
        print(f"💥 Fast BOT image error: {e}")
        return jsonify({"error": str(e)}), 500
    
    
    
def list_objects_in_folder(folder_path):
    """Получает список объектов в указанной папке Minio"""
    try:
        objects = minio_client.list_objects("journals", prefix=folder_path + "/", recursive=True)
        file_names = []
        
        for obj in objects:
            # Извлекаем только имя файла из полного пути
            full_path = obj.object_name
            if full_path.endswith('/'):
                continue  # Пропускаем папки
                
            file_name = full_path.split('/')[-1]  # Берем последнюю часть пути
            file_names.append(file_name)
        
        print(f"📁 Found {len(file_names)} files in {folder_path}: {file_names}")
        return file_names
        
    except Exception as e:
        print(f"❌ Error listing objects in {folder_path}: {e}")
        return []
    
    
    

@minio_bp.route('/fast_bot_content/<path:image_path>')
def fast_bot_content(image_path):
    """Супер-быстрый прокси для контента бота (описание, контакты)"""
    try:
        print(f"🚀 Fast BOT CONTENT image requested: {image_path}")
        
        # Генерируем presigned URL для бакета bot-content
        presigned_url = minio_client.presigned_get_object(
            "bot-content", 
            image_path, 
            expires=timedelta(hours=24)
        )
        
        # Скачиваем изображение
        response = requests.get(presigned_url, timeout=3, stream=True)
        
        print(f"📡 Minio response status: {response.status_code}")
        
        if response.status_code == 200:
            # Определяем content type
            content_type = response.headers.get('Content-Type', 'image/jpeg')
            if not content_type.startswith('image/'):
                if image_path.lower().endswith('.png'):
                    content_type = 'image/png'
                elif image_path.lower().endswith(('.jpg', '.jpeg')):
                    content_type = 'image/jpeg'
                elif image_path.lower().endswith('.gif'):
                    content_type = 'image/gif'
                else:
                    content_type = 'image/jpeg'
            
            # Возвращаем с агрессивным кэшированием
            return Response(
                response.iter_content(chunk_size=8192),
                content_type=content_type,
                headers={
                    'Cache-Control': 'public, max-age=86400',
                    'Access-Control-Allow-Origin': '*',
                    'CDN-Cache-Control': 'public, max-age=86400'
                }
            )
        else:
            print(f"❌ Minio error: {response.text}")
            return jsonify({"error": "Image not found"}), 404
            
    except Exception as e:
        print(f"💥 Fast BOT CONTENT image error: {e}")
        return jsonify({"error": str(e)}), 500
    
    
    
    
@minio_bp.route('/fast_bot_journal/<path:image_path>')
def fast_bot_journal(image_path):
    """Упрощенный быстрый прокси для журналов"""
    try:
        print(f"🚀 Fast BOT JOURNAL: {image_path}")
        
        # Генерируем presigned URL - БЕЗ КЭША НА ДИСКЕ
        presigned_url = minio_client.presigned_get_object(
            "journals-bot", 
            image_path, 
            expires=timedelta(hours=24)
        )
        
        # Скачиваем изображение с коротким таймаутом
        response = requests.get(presigned_url, timeout=5, stream=True)
        
        print(f"📡 Minio response status: {response.status_code}")
        
        if response.status_code == 200:
            # Определяем Content-Type по расширению (быстрее чем headers)
            if image_path.lower().endswith('.png'):
                content_type = 'image/png'
            elif image_path.lower().endswith(('.jpg', '.jpeg')):
                content_type = 'image/jpeg'
            elif image_path.lower().endswith('.gif'):
                content_type = 'image/gif'
            else:
                content_type = 'image/jpeg'
            
            # Возвращаем сразу без кэширования на диске
            return Response(
                response.iter_content(chunk_size=16384),
                content_type=content_type,
                headers={
                    'Cache-Control': 'public, max-age=3600', 
                    'Access-Control-Allow-Origin': '*'
                }
            )
        else:
            print(f"❌ Minio error: {response.status_code}")
            return jsonify({"error": "Image not found"}), 404
            
    except requests.exceptions.Timeout:
        print(f"⏰ Timeout fetching image: {image_path}")
        return jsonify({"error": "Timeout"}), 504
    except Exception as e:
        print(f"💥 Fast BOT JOURNAL error: {e}")
        return jsonify({"error": str(e)}), 500
    
    
    
    
