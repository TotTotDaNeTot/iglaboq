from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse

from datetime import datetime

from utils.minio_client import minio_client
from typing import List, Optional

from io import BytesIO

import uuid
import os



router = APIRouter(prefix="/api/bot-content", tags=["bot-content"])

db = None




@router.post("/upload-image")
async def upload_image(
    request: Request,
    image: UploadFile = File(...),
    content_type: str = Form(...), 
):
    
    current_user = request.state.user
    
    """Загрузить изображение для контента бота"""
    try:
        # 🔐 ПРОВЕРКА ПРАВ
        if not current_user.get('is_staff', False):
            raise HTTPException(status_code=403, detail="Недостаточно прав")

        print(f"📨 Получен запрос upload-image от пользователя {current_user.get('username')}")
        print(f"📦 Content type: {content_type}")
        print(f"📁 File: {image.filename}, Size: {image.size}")
        
        if not content_type:
            raise HTTPException(status_code=400, detail="Content type required")
        
        if not image.filename:
            raise HTTPException(status_code=400, detail="No selected file")
        
        # Проверяем тип файла
        allowed_extensions = {'.jpg', '.jpeg', '.webp', '.gif'}
        file_extension = os.path.splitext(image.filename)[1].lower()
        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=400, 
                detail=f"Неподдерживаемый формат. Разрешены: {', '.join(allowed_extensions)}"
            )
        
        # Проверяем размер файла (макс 10MB)
        max_size = 10 * 1024 * 1024
        file_content = await image.read()
        if len(file_content) > max_size:
            raise HTTPException(status_code=400, detail="Файл слишком большой (макс 10MB)")
        
        # 🔥 ВОЗВРАЩАЕМ КУРСОР НА НАЧАЛО ДЛЯ ПОВТОРНОГО ЧТЕНИЯ
        image_stream = BytesIO(file_content)
        
        # Проверяем/создаем контент
        content = await db.fetch_one(
            "SELECT * FROM bot_content WHERE content_type = %s",
            (content_type,)
        )
        
        if not content:
            await db.execute(
                "INSERT INTO bot_content (content_type, text_content) VALUES (%s, '')",
                (content_type,)
            )
            result = await db.fetch_one("SELECT LAST_INSERT_ID() as id")
            content_id = result['id']
            print(f"✅ Создан новый контент: {content_id}")
        else:
            content_id = content['id']
            print(f"✅ Найден существующий контент: {content_id}")
        
        # Загружаем в MinIO
        unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{file_extension}"
        object_name = f"{content_type}/{unique_filename}"
        
        print(f"🔄 Загрузка в MinIO: {object_name}")
        
        minio_client.put_object(
            "bot-content",
            object_name,
            image_stream,  # ← объект с методом read()
            length=len(file_content),  # ← явно указываем размер
            content_type=image.content_type
        )
        
        image_url = f"https://dismally-familiar-sharksucker.cloudpub.ru/fast_bot_content/{object_name}"
        print(f"✅ Изображение загружено: {image_url}")
        
        # Сохраняем в базу
        await db.execute(
            "INSERT INTO bot_images (content_id, image_url, is_main) VALUES (%s, %s, FALSE)",
            (content_id, image_url)
        )
        
        print("✅ Изображение сохранено в БД")
        
        return JSONResponse({
            "success": True, 
            "message": "Image uploaded successfully",
            "image_url": image_url
        })
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Ошибка при загрузке изображения: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")



@router.post("/delete-image")
async def delete_image(
    request: Request,
    image_id: str = Form(...)
):
    
    current_user = request.state.user
    
    """Удалить изображение"""
    try:
        # 🔐 ПРОВЕРКА ПРАВ
        if not current_user.get('is_staff', False):
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        
        if not image_id:
            raise HTTPException(status_code=400, detail="Image ID required")
        
        # Получаем информацию об изображении
        image = await db.fetch_one(
            "SELECT * FROM bot_images WHERE id = %s",
            (image_id,)
        )
        
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        
        print(f"🗑️ Deleting image: {image['image_url']}")
        
        # Удаляем из MinIO
        image_url = image['image_url']
        
        if 'fast_image_bot/' in image_url:
            object_path = image_url.split('fast_image_bot/')[1]
            bucket_name = "journals-bot"
        elif 'fast_bot_content/' in image_url:
            object_path = image_url.split('fast_bot_content/')[1]
            bucket_name = "bot-content"
        else:
            object_path = image_url.split('fast_image/')[1] if 'fast_image/' in image_url else image_url
            bucket_name = "journals-bot"
        
        print(f"🔍 Bucket: {bucket_name}, Object: {object_path}")
        
        try:
            minio_client.remove_object(bucket_name, object_path)
            print(f"✅ Deleted from MinIO: {object_path}")
        except Exception as e:
            print(f"⚠️ MinIO deletion error (maybe already deleted): {e}")
        
        # Удаляем из базы
        await db.execute(
            "DELETE FROM bot_images WHERE id = %s",
            (image_id,)
        )
        
        print("✅ Deleted from database")
        return JSONResponse({"success": True, "message": "Image deleted"})
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error deleting image: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")



@router.post("/set-main-image")
async def set_main_image(
    request: Request,
    image_id: str
):
    
    current_user = request.state.user
    
    """Сделать изображение главным"""
    try:
        # 🔐 ПРОВЕРКА ПРАВ
        if not current_user.get('is_staff', False):
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        
        if not image_id:
            raise HTTPException(status_code=400, detail="Image ID required")
        
        # Получаем content_id изображения
        image = await db.fetch_one(
            "SELECT content_id FROM bot_images WHERE id = %s",
            (image_id,)
        )
        
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        
        # Сбрасываем все is_main для этого контента
        await db.execute(
            "UPDATE bot_images SET is_main = FALSE WHERE content_id = %s",
            (image['content_id'],)
        )
        
        # Устанавливаем новое главное изображение
        await db.execute(
            "UPDATE bot_images SET is_main = TRUE WHERE id = %s",
            (image_id,)
        )
        
        return JSONResponse({"success": True, "message": "Main image set"})
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")



@router.get("/{content_type}")
async def get_bot_content_api(content_type: str):
    """API для получения контента (для админки)"""
    try:
        content = await db.fetch_one(
            "SELECT * FROM bot_content WHERE content_type = %s", 
            (content_type,)
        )
        
        if not content:
            return JSONResponse({"content": None, "images": [], "buttons": []})
        
        images = await db.fetch_all(
            "SELECT * FROM bot_images WHERE content_id = %s ORDER BY is_main DESC, id",
            (content['id'],)
        )
        
        buttons = []
        if content_type == 'contacts':
            buttons = await db.fetch_all(
                "SELECT * FROM bot_buttons WHERE content_id = %s ORDER BY position",
                (content['id'],)
            )
        
        return JSONResponse({
            "content": content,
            "images": images,
            "buttons": buttons
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")



@router.post("/{content_type}")
async def update_bot_content_api(
    request: Request,
    content_type: str,
    text: str = Form(""),
    button_text: Optional[List[str]] = Form(None),
    button_url: Optional[List[str]] = Form(None)
):
    current_user = request.state.user
    
    """API для обновления контента - принимает FormData"""
    try:
        # 🔐 ПРОВЕРКА ПРАВ
        if not current_user.get('is_staff', False):
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        
        # 🔥 ВСЕ ОПЕРАЦИИ В ОДНОЙ ТРАНЗАКЦИИ
        async with db.transaction() as cursor:
            # 1. Находим или создаем контент
            await cursor.execute(
                "SELECT * FROM bot_content WHERE content_type = %s FOR UPDATE", 
                (content_type,)
            )
            content = await cursor.fetchone()
            
            if content:
                # 2. Обновляем существующий контент
                await cursor.execute(
                    "UPDATE bot_content SET text_content = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (text, content['id'])
                )
                content_id = content['id']
                print(f"✅ Updated existing content: {content_id}")
            else:
                # 3. Создаем новый контент
                await cursor.execute(
                    "INSERT INTO bot_content (content_type, text_content) VALUES (%s, %s)",
                    (content_type, text)
                )
                content_id = cursor.lastrowid
                print(f"✅ Created new content: {content_id}")
            
            # 4. Обработка кнопок (для contacts)
            if content_type == 'contacts':
                # 5. Удаляем старые кнопки
                await cursor.execute(
                    "DELETE FROM bot_buttons WHERE content_id = %s",
                    (content_id,)
                )
                print(f"🗑️ Deleted old buttons for content: {content_id}")
                
                # 6. Добавляем новые кнопки
                if button_text and button_url:
                    inserted_count = 0
                    for i in range(len(button_text)):
                        if i < len(button_url) and button_text[i] and button_url[i]:
                            await cursor.execute(
                                "INSERT INTO bot_buttons (content_id, button_text, button_url, position) VALUES (%s, %s, %s, %s)",
                                (content_id, button_text[i], button_url[i], i)
                            )
                            inserted_count += 1
                    print(f"✅ Inserted {inserted_count} new buttons")
        
        return JSONResponse({"success": True})
        
    except Exception as e:
        print(f"❌ Error updating bot content: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
    

