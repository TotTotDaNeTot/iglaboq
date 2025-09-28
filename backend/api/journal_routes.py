from flask import Blueprint, request, jsonify, current_app

from datetime import timedelta

from database import db
from utils.minio_client import minio_client

from authentication.jwt_auth.decorators import jwt_required

import logging



journal_bp = Blueprint('journal', __name__)


logger = logging.getLogger(__name__)




def run_async(coro):
    """Используем глобальную функцию run_async из app"""
    return current_app.run_async(coro)
        
        
        
        
@journal_bp.route('/')
def home():
    return """
    <h1>API для магазина журналов</h1>
    <p>Доступные эндпоинты:</p>
    <ul>
        <li><a href="/get_journal?id=1">/get_journal?id=1</a></li>
        <li><a href="/check_stock?journal_id=1&quantity=2">/check_stock?journal_id=1&quantity=2</a></li>
    </ul>
    """
            
        

@journal_bp.route('/get_journal_images')
def get_journal_images():
    try:
        journal_id = request.args.get('id')
        if not journal_id:
            return jsonify({"error": "Journal ID is required"}), 400
        
        # Получаем все изображения журнала из БД
        images = run_async(db.fetch_all(
            "SELECT image_url FROM journal_images WHERE journal_id = %s ORDER BY is_main DESC, id",
            (journal_id,)
        ))
        
        response = jsonify({
            'images': [img['image_url'] for img in images],
            'count': len(images)
        })
        
        # Запрет кэширования
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting images for journal {journal_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500
    
    
    
@journal_bp.route('/get_journal')
def get_journal():
    try:
        journal_id = request.args.get('id')
        if not journal_id:
            return jsonify({"error": "Journal ID is required"}), 400
        
        # Получаем все данные из БД
        journal_data = run_async(db.fetch_one(
            "SELECT id, title, year, description, price, quantity FROM journals WHERE id = %s", 
            (journal_id,)
        ))
        
        if not journal_data:
            return jsonify({"error": "Journal not found"}), 404
        
        response = jsonify({
            'id': journal_data['id'],
            'title': journal_data['title'],
            'year': journal_data['year'],
            'description': journal_data['description'],
            'price': float(journal_data['price']),
            'quantity': int(journal_data['quantity'])
        })
        
        # ЗАПРЕТ КЭШИРОВАНИЯ
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting journal {journal_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500
    
    
    
@journal_bp.route('/get_presigned_url')
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
    
    
    
@journal_bp.route('/get_journal_images_presigned/<int:journal_id>')
def get_journal_images_presigned(journal_id):
    """Возвращает быстрые URL для обычных изображений журнала (для мини-приложения)"""
    try:
        # Получаем пути изображений из БД
        images = run_async(db.fetch_all(
            "SELECT image_url FROM journal_images WHERE journal_id = %s ORDER BY is_main DESC, id",
            (journal_id,)
        ))
        
        if not images:
            return jsonify({"images": []})
        
        fast_urls = []
        for img in images:
            image_url = img['image_url']
            
            # ПРЕОБРАЗУЕМ В БЫСТРЫЕ URL ДЛЯ ОБЫЧНЫХ ИЗОБРАЖЕНИЙ
            if 'minio_proxy/journals/' in image_url:
                # Из: https://dismally-familiar-sharksucker.cloudpub.ru/minio_proxy/journals/journal_3/filename.png
                # В: https://dismally-familiar-sharksucker.cloudpub.ru/fast_image/journal_3/filename.png
                object_path = image_url.split('minio_proxy/journals/')[1]
                fast_url = f"https://dismally-familiar-sharksucker.cloudpub.ru/fast_image/{object_path}"
                fast_urls.append(fast_url)
            elif 'fast_image/' in image_url:
                # Если уже правильный формат
                fast_urls.append(image_url)
            else:
                # Другие форматы оставляем как есть
                fast_urls.append(image_url)
        
        print(f"🚀 Generated {len(fast_urls)} fast URLs for journal {journal_id} (mini-app)")
        print(f"📋 URLs: {fast_urls}")
        return jsonify({"images": fast_urls})
        
    except Exception as e:
        print(f"❌ Error getting fast URLs for mini-app: {e}")
        return jsonify({"error": str(e)}), 500
    
    
    
@journal_bp.route('/fix_journal_images/<int:journal_id>', methods=['POST'])
@jwt_required 
def fix_journal_images(journal_id):
    """Исправляет URL изображений журнала в базе данных"""
    
    # 🔥 ПРОВЕРКА ПРАВ
    current_user = request.jwt_user
    if not current_user.get('is_staff'):
        return jsonify({"success": False, "error": "Insufficient permissions"}), 403
    
    connection = None
    cursor = None
    
    try:
        # Получаем правильные URL из API
        response = get_journal_images_presigned(journal_id)
        correct_images = response.get_json()
        
        if not correct_images or 'images' not in correct_images:
            return jsonify({"success": False, "error": "No images found in API"})
        
        # 🔥 НАЧИНАЕМ ТРАНЗАКЦИЮ
        connection = db.get_connection()
        cursor = connection.cursor(dictionary=True)
        connection.autocommit = False
        
        try:
            # Получаем текущие изображения из БД внутри транзакции
            cursor.execute(
                "SELECT id, image_url FROM journal_images WHERE journal_id = %s ORDER BY id",
                (journal_id,)
            )
            current_images = cursor.fetchall()
            
            if not current_images:
                connection.rollback()
                return jsonify({"success": False, "error": "No images in database"})
            
            if len(current_images) != len(correct_images['images']):
                connection.rollback()
                return jsonify({
                    "success": False, 
                    "error": f"Image count mismatch: DB has {len(current_images)}, API has {len(correct_images['images'])}"
                })
            
            # Обновляем каждый URL в базе данных внутри транзакции
            updated_count = 0
            for i, (db_image, correct_url) in enumerate(zip(current_images, correct_images['images'])):
                # Обновляем только если URL отличается
                if db_image['image_url'] != correct_url:
                    cursor.execute(
                        "UPDATE journal_images SET image_url = %s WHERE id = %s",
                        (correct_url, db_image['id'])
                    )
                    print(f"✅ Updated image {db_image['id']}: {correct_url}")
                    updated_count += 1
                else:
                    print(f"ℹ️ Image {db_image['id']} already has correct URL")
            
            # 🔥 КОММИТИМ ТРАНЗАКЦИЮ
            connection.commit()
            return jsonify({
                "success": True, 
                "updated": updated_count,
                "total": len(current_images)
            })
            
        except Exception as e:
            # 🔥 ОТКАТЫВАЕМ ПРИ ОШИБКЕ
            if connection:
                connection.rollback()
            raise e
            
    except Exception as e:
        print(f"❌ Error fixing images: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
        
    finally:
        # Освобождаем ресурсы
        if cursor:
            cursor.close()
        if connection:
            connection.close()
    
    
    
@journal_bp.route('/debug_images/<int:journal_id>')
def debug_images(journal_id):
    """Отладочная информация по изображениям"""
    try:
        # Получаем изображения из БД
        images = run_async(db.fetch_all(
            "SELECT id, image_url FROM journal_images WHERE journal_id = %s",
            (journal_id,)
        ))
        
        result = {
            "journal_id": journal_id,
            "images_in_db": images,
            "presigned_urls": []
        }
        
        # Генерируем presigned URLs
        for img in images:
            image_url = img['image_url']
            
            if 'minio_proxy/journals/' in image_url:
                object_path = image_url.split('minio_proxy/journals/')[1]
            else:
                object_path = image_url
            
            # Пробуем сгенерировать presigned URL
            try:
                presigned_url = minio_client.presigned_get_object(
                    "journals",
                    object_path,
                    expires=timedelta(hours=1)
                )
                result["presigned_urls"].append({
                    "original_url": image_url,
                    "object_path": object_path,
                    "presigned_url": presigned_url,
                    "status": "success"
                })
            except Exception as e:
                result["presigned_urls"].append({
                    "original_url": image_url,
                    "object_path": object_path,
                    "error": str(e),
                    "status": "failed"
                })
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500    
    


@journal_bp.route('/check_stock')
def check_stock():
    try:
        journal_id = request.args.get('journal_id', type=int)
        quantity = request.args.get('quantity', default=1, type=int)
        
        journal = run_async(db.fetch_one(
            "SELECT quantity FROM journals WHERE id = %s", 
            (journal_id,)
        ))
        
        if not journal:
            return jsonify({"error": "Журнал не найден"}), 404
        
        available = journal['quantity'] >= quantity
        return jsonify({
            "available": available,
            "in_stock": journal['quantity'],
            "required": quantity,
            "message": "Достаточно" if available else f"Недостаточно. В наличии: {journal['quantity']}"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    
    
    
# Функции для получения данных журнала
def get_journal_title(journal_id):
    """Получает название журнала из БД"""
    try:
        result = run_async(db.fetch_one(
            "SELECT title FROM journals WHERE id = %s", 
            (journal_id,)
        ))
        return result['title'] if result else "Журнал"
    except Exception as e:
        logger.error(f"Error getting title for journal {journal_id}: {str(e)}")
        return "Журнал"



def get_journal_year(journal_id):
    """Получает год выпуска журнала из БД"""
    try:
        result = run_async(db.fetch_one(
            "SELECT year FROM journals WHERE id = %s", 
            (journal_id,)
        ))
        return result['year'] if result else "—"
    except Exception as e:
        logger.error(f"Error getting year for journal {journal_id}: {str(e)}")
        return "—"



def get_journal_description(journal_id):
    """Получает описание журнала из БД"""
    try:
        result = run_async(db.fetch_one(
            "SELECT description FROM journals WHERE id = %s", 
            (journal_id,)
        ))
        return result['description'] if result else "Описание отсутствует"
    except Exception as e:
        logger.error(f"Error getting description for journal {journal_id}: {str(e)}")
        return "Описание отсутствует"



def get_journal_price(journal_id):
    """Получает цену журнала из БД"""
    try:
        result = run_async(db.fetch_one(
            "SELECT price FROM journals WHERE id = %s", 
            (journal_id,)
        ))
        return float(result['price']) if result else 0.0
    except Exception as e:
        logger.error(f"Error getting price for journal {journal_id}: {str(e)}")
        return 0.0



def get_journal_quantity(journal_id):
    """Получает актуальное количество журналов из БД"""
    try:
        result = run_async(db.fetch_one(
            "SELECT quantity FROM journals WHERE id = %s", 
            (journal_id,)
        ))
        return int(result['quantity']) if result else 0
    except Exception as e:
        logger.error(f"Error getting quantity for journal {journal_id}: {str(e)}")
        return 0
    
    