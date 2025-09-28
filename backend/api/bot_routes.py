from flask import Blueprint, request, jsonify, current_app

from database import db
from utils.minio_client import minio_client

from authentication.jwt_auth.decorators import jwt_required

import logging
import os




bot_bp = Blueprint('bot', __name__)
logger = logging.getLogger(__name__)




def run_async(coro):
    """Используем глобальную функцию run_async из app"""
    return current_app.run_async(coro)



@bot_bp.route('/get_journal_bot_images/<int:journal_id>')
def get_journal_bot_images(journal_id):
    """Возвращает быстрые URL для изображений бота"""
    try:
        # Получаем пути изображений из БД ДЛЯ БОТА
        images = run_async(db.fetch_all(
            "SELECT image_url FROM journal_bot_images WHERE journal_id = %s ORDER BY is_main DESC, id",
            (journal_id,)
        ))
        
        if not images:
            return jsonify({"images": []})
        
        fast_urls = []
        for img in images:
            image_url = img['image_url']
            
            if 'fast_image_bot/' in image_url:
                # Уже правильный формат
                fast_urls.append(image_url)
            else:
                # Если URL в другом формате, преобразуем
                object_path = image_url.split('fast_image/')[1] if 'fast_image/' in image_url else image_url
                fast_url = f"https://dismally-familiar-sharksucker.cloudpub.ru/fast_image_bot/{object_path}"
                fast_urls.append(fast_url)
        
        print(f"🚀 Generated {len(fast_urls)} fast URLs for BOT journal {journal_id}")
        print(f"📋 URLs: {fast_urls}")
        return jsonify({"images": fast_urls})
        
    except Exception as e:
        print(f"❌ Error getting BOT fast URLs: {e}")
        return jsonify({"error": str(e)}), 500
    
    
    
@bot_bp.route('/upload_bot_image', methods=['POST'])
@jwt_required
def upload_bot_image():
    # Пользователь уже аутентифицирован декоратором
    current_user = request.jwt_user  # ← Пользователь из декоратора
    
    # 🔥 ДОБАВЛЯЕМ ПРОВЕРКУ ПРАВ
    if not current_user.get('is_staff'):
        return jsonify({"error": "Insufficient permissions"}), 403
    
    try:
        journal_id = request.form.get('journal_id')
        if not journal_id:
            return jsonify({"error": "Journal ID is required"}), 400
        
        if 'image' not in request.files:
            return jsonify({"error": "No image file"}), 400
        
        image_file = request.files['image']
        if image_file.filename == '':
            return jsonify({"error": "No selected file"}), 400
        
        # 🔥 ГЕНЕРИРУЕМ УНИКАЛЬНОЕ ИМЯ ФАЙЛА
        import uuid
        import datetime
        file_extension = os.path.splitext(image_file.filename)[1].lower()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{uuid.uuid4().hex[:8]}{file_extension}"
        
        object_name = f"journal_{journal_id}/{unique_filename}"
        
        # Загружаем в MinIO
        minio_client.put_object(
            "journals-bot",
            object_name,
            image_file,
            length=-1,
            part_size=10*1024*1024,
            content_type=image_file.content_type
        )
        
        # Сохраняем URL в БД
        image_url = f"https://dismally-familiar-sharksucker.cloudpub.ru/fast_image_bot/{object_name}"
        
        run_async(db.execute(
            "INSERT INTO journal_bot_images (journal_id, image_url, is_main) VALUES (%s, %s, %s)",
            (journal_id, image_url, False)
        ))
        
        print(f"✅ Uploaded bot image: {image_url}")
        return jsonify({"success": True, "image_url": image_url})
        
    except Exception as e:
        print(f"❌ Error uploading bot image: {e}")
        return jsonify({"error": str(e)}), 500
    
    

@bot_bp.route('/set_main_bot_image', methods=['POST'])
@jwt_required
def set_main_bot_image():
    connection = None
    cursor = None
    
    # Пользователь уже аутентифицирован декоратором
    current_user = request.jwt_user  # ← Пользователь из декоратора
    
    # 🔥 ДОБАВЛЯЕМ ПРОВЕРКУ ПРАВ
    if not current_user.get('is_staff'):
        return jsonify({"error": "Insufficient permissions"}), 403
    
    try:
        journal_id = request.json.get('journal_id')
        image_id = request.json.get('image_id')
        
        # 🔥 СИНХРОННАЯ ТРАНЗАКЦИЯ
        connection = db.get_connection()
        cursor = connection.cursor(dictionary=True)
        connection.autocommit = False
        
        cursor.execute(
            "UPDATE journal_bot_images SET is_main = FALSE WHERE journal_id = %s",
            (journal_id,)
        )
        cursor.execute(
            "UPDATE journal_bot_images SET is_main = TRUE WHERE id = %s AND journal_id = %s",
            (image_id, journal_id)
        )
        
        connection.commit()
        return jsonify({"success": True})
            
    except Exception as e:
        if connection:
            connection.rollback()
        return jsonify({"error": str(e)}), 500
        
    finally:
        if cursor: cursor.close()
        if connection: connection.close()



@bot_bp.route('/delete_bot_image', methods=['POST'])
@jwt_required
def delete_bot_image():
    
    # Пользователь уже аутентифицирован декоратором
    current_user = request.jwt_user  # ← Пользователь из декоратора
    
    # 🔥 ДОБАВЛЯЕМ ПРОВЕРКУ ПРАВ
    if not current_user.get('is_staff'):
        return jsonify({"error": "Insufficient permissions"}), 403
    
    try:
        image_id = request.json.get('image_id')
        
        # Получаем информацию об изображении
        image = run_async(db.fetch_one(
            "SELECT image_url FROM journal_bot_images WHERE id = %s",
            (image_id,)
        ))
        
        if image:
            # 🔥 ПРАВИЛЬНОЕ ИЗВЛЕЧЕНИЕ ПУТИ ИЗ URL
            image_url = image['image_url']
            if 'fast_image_bot/' in image_url:
                object_path = image_url.split('fast_image_bot/')[1]
            else:
                # Если старый формат URL
                object_path = image_url.split('fast_image/')[1] if 'fast_image/' in image_url else image_url
            
            print(f"🗑️ Deleting from MinIO: {object_path}")
            
            # Удаляем из MinIO
            try:
                minio_client.remove_object("journals-bot", object_path)
                print(f"✅ Deleted from MinIO: {object_path}")
            except Exception as e:
                print(f"⚠️ MinIO deletion error (maybe already deleted): {e}")
            
            # Удаляем из БД
            run_async(db.execute(
                "DELETE FROM journal_bot_images WHERE id = %s",
                (image_id,)
            ))
        
        return jsonify({"success": True})
        
    except Exception as e:
        print(f"❌ Error deleting bot image: {e}")
        return jsonify({"error": str(e)}), 500
    
    

# Дополнительные полезные endpoint'ы для бота
@bot_bp.route('/get_bot_images_info/<int:journal_id>')
def get_bot_images_info(journal_id):
    """Получает полную информацию о изображениях бота"""
    try:
        images = run_async(db.fetch_all(
            "SELECT id, image_url, is_main, created_at FROM journal_bot_images WHERE journal_id = %s ORDER BY is_main DESC, created_at DESC",
            (journal_id,)
        ))
        
        return jsonify({"images": images})
        
    except Exception as e:
        print(f"❌ Error getting bot images info: {e}")
        return jsonify({"error": str(e)}), 500



@bot_bp.route('/get_main_bot_image/<int:journal_id>')
def get_main_bot_image(journal_id):
    """Получает главное изображение бота для журнала"""
    try:
        image = run_async(db.fetch_one(
            "SELECT image_url FROM journal_bot_images WHERE journal_id = %s AND is_main = TRUE",
            (journal_id,)
        ))
        
        if image:
            return jsonify({"main_image": image['image_url']})
        else:
            # Если нет главного, возвращаем первое изображение
            first_image = run_async(db.fetch_one(
                "SELECT image_url FROM journal_bot_images WHERE journal_id = %s ORDER BY id LIMIT 1",
                (journal_id,)
            ))
            if first_image:
                return jsonify({"main_image": first_image['image_url']})
            else:
                return jsonify({"main_image": None})
                
    except Exception as e:
        print(f"❌ Error getting main bot image: {e}")
        return jsonify({"error": str(e)}), 500