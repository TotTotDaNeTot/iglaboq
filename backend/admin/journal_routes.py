from fastapi import APIRouter, Request, Form, File, UploadFile, HTTPException, Depends
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from typing import List, Optional

from backend.services.minio_service import minio_service

import aiomysql



router = APIRouter(prefix="/journal", tags=["journal"])

templates: Jinja2Templates = None
db = None




# Journals Management Routes
@router.get("/list")
async def journals_list(request: Request, message: str = None):
    
    current_user = request.state.user
    
    if not current_user.get('is_staff', False):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    
    journals = await db.fetch_all("""
        SELECT id, title, description, price, year, created_at, quantity 
        FROM journals ORDER BY year DESC, created_at DESC
    """)
    
    return templates.TemplateResponse(
        "journals/journals_list.html", 
        {
            "request": request, 
            "journals": journals, 
            "user": current_user,
            "message": message  # ← Передаем сообщение
        }
    )



@router.get("/add")
async def add_journal_form(request: Request):
    # Используйте get_current_user который принимает Request
    current_user = request.state.user
    
    if not current_user.get('is_staff', False):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    from datetime import datetime
    current_year = datetime.now().year
    
    return templates.TemplateResponse(
        "journals/add_journal.html", 
        {
            "request": request, 
            "current_year": current_year,
            "user": current_user 
        }
    )



@router.post("/add")
async def add_journal(
    request: Request,
    journal_id: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    year: int = Form(...),
    quantity: int = Form(0)
):
    # Проверяем аутентификацию
    current_user = request.state.user
    
    if not current_user.get('is_staff', False):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    try:
        # Проверяем, существует ли уже журнал с таким ID
        existing = await db.fetch_one(
            "SELECT 1 FROM journals WHERE id = %s", (journal_id,)
        )
        if existing:
            # Вместо исключения возвращаем шаблон с ошибкой
            from datetime import datetime
            current_year = datetime.now().year
            
            return templates.TemplateResponse(
                "journals/add_journal.html", 
                {
                    "request": request,
                    "current_year": current_year,
                    "user": current_user,
                    "error": f"Журнал с ID {journal_id} уже существует!",
                    "form_data": {  # Сохраняем введенные данные
                        "journal_id": journal_id,
                        "title": title,
                        "description": description,
                        "price": price,
                        "year": year,
                        "quantity": quantity
                    }
                }
            )
        
        # Добавляем в БД
        await db.execute(
            """INSERT INTO journals 
            (id, title, description, price, year, quantity) 
            VALUES (%s, %s, %s, %s, %s, %s)""",
            (journal_id, title, description, price, year, quantity)
        )
        
        return RedirectResponse(url="/journal/list", status_code=303)
        
    except Exception as e:
        from datetime import datetime
        current_year = datetime.now().year
        
        return templates.TemplateResponse(
            "journals/add_journal.html", 
            {
                "request": request,
                "current_year": current_year,
                "user": current_user,
                "error": f"Ошибка при создании журнала: {str(e)}",
                "form_data": {
                    "journal_id": journal_id,
                    "title": title,
                    "description": description,
                    "price": price,
                    "year": year,
                    "quantity": quantity
                }
            }
        )



@router.get("/{journal_id}/edit")
async def edit_journal_form(
    request: Request, 
    journal_id: str,
):
    
    current_user = request.state.user
    
    if not current_user.get('is_staff', False):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    journal = await db.fetch_one("SELECT * FROM journals WHERE id = %s", (journal_id,))
    if not journal:
        raise HTTPException(status_code=404, detail="Journal not found")
    
    from datetime import datetime
    current_year = datetime.now().year
    
    # Загружаем изображения
    journal_images = await db.fetch_all(
        "SELECT * FROM journal_images WHERE journal_id = %s ORDER BY is_main DESC, id",
        (journal_id,)
    )
    journal['images'] = journal_images
    
    # Загружаем изображения бота
    journal_bot_images = await db.fetch_all(
        "SELECT * FROM journal_bot_images WHERE journal_id = %s ORDER BY is_main DESC, id",
        (journal_id,)
    )
    journal['bot_images'] = journal_bot_images
    
    return templates.TemplateResponse(
        "journals/edit_journal.html", 
        {
            "request": request, 
            "current_year": current_year,
            "journal": journal,
            "user": current_user 
        }
    )



@router.post("/{journal_id}/edit")
async def edit_journal(
    request: Request,
    journal_id: str,
    new_id: Optional[str] = Form(None),
    title: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    year: int = Form(...),
    quantity: int = Form(0),
    new_images: Optional[List[UploadFile]] = File(None),
    new_bot_images: Optional[List[UploadFile]] = File(None),
    set_first_bot_as_main: Optional[bool] = Form(False),
    delete_images: Optional[List[str]] = Form(None),
    delete_bot_images: Optional[List[str]] = Form(None),
    main_image: Optional[str] = Form(None),
    main_bot_image: Optional[str] = Form(None)
):
    
    current_user = request.state.user
    
    if not current_user.get('is_staff', False):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    try:
        async with db.transaction() as cursor:
            # 🔒 БЛОКИРУЕМ ТЕКУЩИЙ ЖУРНАЛ НА ЗАПИСЬ
            await cursor.execute(
                "SELECT * FROM journals WHERE id = %s FOR UPDATE", 
                (journal_id,)
            )
            journal = await cursor.fetchone()
            
            if not journal:
                raise HTTPException(status_code=404, detail="Journal not found")
            
            # ЕСЛИ МЕНЯЕМ ID - БЛОКИРУЕМ И НОВЫЙ ID
            if new_id and new_id != journal_id:
                await cursor.execute(
                    "SELECT 1 FROM journals WHERE id = %s FOR UPDATE", 
                    (new_id,)
                )
                existing = await cursor.fetchone()
                
                if existing:
                    raise HTTPException(status_code=400, detail="Journal with this ID already exists")
                
                # 🔄 ОБНОВЛЯЕМ ID (под защитой блокировки)
                await cursor.execute(
                    "UPDATE journals SET id = %s WHERE id = %s",
                    (new_id, journal_id)
                )
                journal_id = new_id
                print(f"✅ Journal ID changed to: {journal_id}")
            
            # 📝 ОБНОВЛЯЕМ ОСНОВНЫЕ ДАННЫЕ
            await cursor.execute(
                """UPDATE journals SET 
                title = %s, description = %s, price = %s, 
                year = %s, quantity = %s 
                WHERE id = %s""",
                (title, description, price, year, quantity, journal_id)
            )
            print(f"✅ Updated journal data: {journal_id}")
            
            # 🖼️ ОБРАБОТКА ИЗОБРАЖЕНИЙ
            if new_images:
                for image_file in new_images:
                    if image_file and image_file.filename:
                        print(f"📤 Processing image: {image_file.filename}")
                        contents = await image_file.read()
                        
                        image_url, filename = minio_service.upload_image(
                            journal_id, contents, image_file.filename
                        )
                        if image_url:
                            await cursor.execute(
                                "INSERT INTO journal_images (journal_id, image_path, image_url) VALUES (%s, %s, %s)",
                                (journal_id, filename, image_url)
                            )
                            print(f"✅ Image uploaded: {image_url}")
            
            if new_bot_images:
                for i, image_file in enumerate(new_bot_images):
                    if image_file and image_file.filename:
                        print(f"📤 Processing bot image: {image_file.filename}")
                        contents = await image_file.read()
                        
                        image_url, filename = minio_service.upload_bot_image(
                            journal_id, contents, image_file.filename
                        )
                        if image_url:
                            is_main = set_first_bot_as_main and i == 0
                            await cursor.execute(
                                "INSERT INTO journal_bot_images (journal_id, image_url, is_main) VALUES (%s, %s, %s)",
                                (journal_id, image_url, is_main)
                            )
                            print(f"✅ Bot image uploaded: {image_url}")
            
            # 🗑️ УДАЛЕНИЕ ИЗОБРАЖЕНИЙ
            if delete_images:
                for image_id in delete_images:
                    await cursor.execute(
                        "SELECT image_path FROM journal_images WHERE id = %s AND journal_id = %s",
                        (image_id, journal_id)
                    )
                    image = await cursor.fetchone()
                    if image:
                        minio_service.delete_image(journal_id, image['image_path'])
                        await cursor.execute(
                            "DELETE FROM journal_images WHERE id = %s", (image_id,)
                        )
                        print(f"🗑️ Deleted image: {image_id}")
            
            if delete_bot_images:
                for image_id in delete_bot_images:
                    await cursor.execute(
                        "SELECT image_url FROM journal_bot_images WHERE id = %s",
                        (image_id,)
                    )
                    image = await cursor.fetchone()
                    if image:
                        object_path = image['image_url'].split('fast_image_bot/')[1]
                        minio_service.delete_bot_image(object_path)
                        await cursor.execute(
                            "DELETE FROM journal_bot_images WHERE id = %s",
                            (image_id,)
                        )
                        print(f"🗑️ Deleted bot image: {image_id}")
            
            # ⭐ ГЛАВНЫЕ ИЗОБРАЖЕНИЯ
            if main_image:
                await cursor.execute(
                    "UPDATE journal_images SET is_main = FALSE WHERE journal_id = %s",
                    (journal_id,)
                )
                await cursor.execute(
                    "UPDATE journal_images SET is_main = TRUE WHERE id = %s AND journal_id = %s",
                    (main_image, journal_id)
                )
                print(f"⭐ Set main image: {main_image}")
            
            if main_bot_image:
                await cursor.execute(
                    "UPDATE journal_bot_images SET is_main = FALSE WHERE journal_id = %s",
                    (journal_id,)
                )
                await cursor.execute(
                    "UPDATE journal_bot_images SET is_main = TRUE WHERE id = %s AND journal_id = %s",
                    (main_bot_image, journal_id)
                )
                print(f"⭐ Set main bot image: {main_bot_image}")
        
        return RedirectResponse(url="/journal/list", status_code=303)
        
    except HTTPException:
        raise
    
    except Exception as e:
        print(f"❌ Error updating journal: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error updating journal: {str(e)}")
        
        


@router.post("/delete/{journal_id}")
async def delete_journal(
    request: Request,
    journal_id: str,
):
    
    current_user = request.state.user
    
    if not current_user.get('is_staff', False):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    try:
        await db.execute("DELETE FROM journals WHERE id = %s", (journal_id,))
        return RedirectResponse(url="/journal/list", status_code=303)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting journal: {str(e)}")

