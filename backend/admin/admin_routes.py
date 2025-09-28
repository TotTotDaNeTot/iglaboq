from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from utils.url_helpers import url_for

from authentication.jwt_auth.token_utils import get_current_user
from utils.minio_client import minio_client
from werkzeug.security import check_password_hash, generate_password_hash
import os
from datetime import datetime
import uuid
import jwt
import asyncio




templates: Jinja2Templates = None
db = None

router = APIRouter(prefix="", tags=["admin"])




# Роуты админ панели
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, token: str = None):

    current_user = request.state.user
    
    # Если есть токен в URL (для редиректа после логина)
    if token and not current_user:
        try:
            payload = jwt.decode(token, os.getenv('ADMIN_SECRET_KEY'), algorithms=["HS256"])
            # Просто логируем, не перезаписываем current_user
            print(f"🎫 Token from URL: {payload}")
        except Exception as e:
            print(f"❌ Invalid token from URL: {e}")
    
    print(f"📊 Dashboard user: {current_user}")
    
    return templates.TemplateResponse(
        "admin/dashboard.html", 
        {
            "request": request, 
            "user": current_user  # ✅ Используем request.state.user
        }
    )



@router.get("/create", response_class=HTMLResponse)
async def create_admin_page(request: Request):
    
    current_user = request.state.user
    
    if not current_user.get('is_staff', False):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    return templates.TemplateResponse(
        "admin/create_admin.html", 
        {
            "request": request,
            "user": current_user 
        }
    )



@router.post("/create")
async def create_admin(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    is_staff: bool = Form(False),
):
    current_user = request.state.user
    
    # Проверяем права: Staff может создавать только обычных админов (is_staff=False)
    # Супер-админ может создавать любых
    if not current_user.get('is_staff', False):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    # 🔒 ЗАЩИТА ОТ СОЗДАНИЯ СУПЕР-АДМИНА
    # Никто не может создать супер-админа через этот эндпоинт
    # Даже если передать is_superuser в запросе - он игнорируется
    
    # Если текущий пользователь Staff (но не супер-админ), проверяем что он не создает Staff
    if current_user.get('is_staff', False) and not current_user.get('is_superuser', False):
        if is_staff:
            raise HTTPException(status_code=403, detail="Staff админ не может создавать других Staff админов")
    
    try:
        password_hash = generate_password_hash(password)
        
        # 🔒 ЯВНО УКАЗЫВАЕМ is_superuser = FALSE для всех создаваемых админов
        await db.execute(
            "INSERT INTO admins (username, password_hash, is_staff, is_superuser) VALUES (%s, %s, %s, %s)",
            (username, password_hash, is_staff, False)  # Всегда is_superuser = False
        )
        return RedirectResponse(url="/admin/list", status_code=303)
        
    except Exception as e:
        error_message = str(e)
        
        if "Duplicate entry" in error_message and "username" in error_message:
            user_friendly_error = f"Администратор с именем '{username}' уже существует!"
        else:
            user_friendly_error = f"Ошибка при создании администратора: {error_message}"
        
        return templates.TemplateResponse(
            "admin/create_admin.html", 
            {
                "request": request,
                "user": current_user,
                "error": user_friendly_error,
                "form_data": {
                    "username": username,
                    "is_staff": is_staff
                }
            }
        )
        


@router.get("/list", response_class=HTMLResponse)
async def admin_list(request: Request):
    
    current_user = request.state.user
    
    if not current_user.get('is_staff', False):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    admins = await db.fetch_all("SELECT id, username, is_staff, is_superuser FROM admins ORDER BY is_superuser DESC, username")
    return templates.TemplateResponse(
        "admin/staff_list.html", 
        {
            "request": request, 
            "admins": admins,
            "user": current_user
        }
    )
    


@router.get("/bot-content", response_class=HTMLResponse)
async def bot_content_admin(request: Request):
    
    current_user = request.state.user
    
    """Страница управления контентом бота"""
    try:
        # Параллельное выполнение запросов для ускорения
        description_content, contacts_content = await asyncio.gather(
            db.fetch_one("SELECT * FROM bot_content WHERE content_type = 'description'"),
            db.fetch_one("SELECT * FROM bot_content WHERE content_type = 'contacts'"),
            return_exceptions=True
        )
        
        # Обрабатываем возможные исключения
        if isinstance(description_content, Exception):
            print(f"Error loading description: {description_content}")
            description_content = None
        if isinstance(contacts_content, Exception):
            print(f"Error loading contacts: {contacts_content}")
            contacts_content = None
        
        # Загружаем изображения и кнопки параллельно
        description_images = []
        contacts_images = []
        contacts_buttons = []
        
        if description_content:
            description_images = await db.fetch_all(
                "SELECT * FROM bot_images WHERE content_id = %s ORDER BY is_main DESC, id",
                (description_content['id'],)
            )
        
        if contacts_content:
            contacts_images, contacts_buttons = await asyncio.gather(
                db.fetch_all(
                    "SELECT * FROM bot_images WHERE content_id = %s ORDER BY is_main DESC, id",
                    (contacts_content['id'],)
                ),
                db.fetch_all(
                    "SELECT * FROM bot_buttons WHERE content_id = %s ORDER BY position",
                    (contacts_content['id'],)
                ),
                return_exceptions=True
            )
            
            # Обрабатываем исключения
            if isinstance(contacts_images, Exception):
                print(f"Error loading contacts images: {contacts_images}")
                contacts_images = []
            if isinstance(contacts_buttons, Exception):
                print(f"Error loading contacts buttons: {contacts_buttons}")
                contacts_buttons = []
        
        return templates.TemplateResponse(
            "bot/admin_bot_content.html",
            {
                "request": request,
                "user": current_user,
                "description_content": description_content,
                "description_images": description_images,
                "contacts_content": contacts_content,
                "contacts_images": contacts_images,
                "contacts_buttons": contacts_buttons
            }
        )
        
    except Exception as e:
        print(f"Error loading bot content: {e}")
        return templates.TemplateResponse(
            "bot/admin_bot_content.html",
            {
                "request": request,
                "user": current_user,
                "description_content": None,
                "description_images": [],
                "contacts_content": None,
                "contacts_images": [],
                "contacts_buttons": []
            }
        )
        


@router.get("/delete/{admin_id}")
async def delete_admin_page(
    request: Request,
    admin_id: int,
):
    
    current_user = request.state.user
    current_user_id = current_user.get('sub')
    
    """Страница подтверждения удаления"""
    if not current_user.get('is_staff', False):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    admin = await db.fetch_one("SELECT * FROM admins WHERE id = %s", (admin_id,))
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    # 🔥 НЕЛЬЗЯ УДАЛИТЬ САМОГО СЕБЯ
    if admin_id == current_user_id:
        raise HTTPException(status_code=403, detail="Cannot delete your own account")
    
    # 🔥 НЕЛЬЗЯ УДАЛИТЬ СУПЕР-АДМИНА (ВООБЩЕ НИКОМУ)
    if admin['is_superuser']:
        raise HTTPException(status_code=403, detail="Cannot delete super admin account")
    
    # 🔥 ОБЫЧНЫЙ STAFF АДМИН МОЖЕТ УДАЛЯТЬ ТОЛЬКО ОБЫЧНЫХ АДМИНОВ
    if not current_user.get('is_superuser', False) and admin['is_staff']:
        raise HTTPException(status_code=403, detail="Staff admins can only delete regular admins")

    return templates.TemplateResponse(
        "admin/delete_admin.html", 
        {
            "request": request,
            "user": current_user,
            "admin": admin
        }
    )



@router.post("/delete/{admin_id}")
async def delete_admin(
    request: Request,
    admin_id: int,
):
    current_user = request.state.user
    
    # 🔒 Проверяем права: удалять могут только Staff и выше
    if not current_user.get('is_staff', False):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    try:
        # Получаем админа для удаления
        admin = await db.fetch_one("SELECT * FROM admins WHERE id = %s", (admin_id,))
        if not admin:
            raise HTTPException(status_code=404, detail="Admin not found")
        
        current_user_id = current_user.get('sub')
        
        # 🔒 НЕЛЬЗЯ УДАЛИТЬ САМОГО СЕБЯ
        if admin_id == current_user_id:
            raise HTTPException(status_code=403, detail="Cannot delete your own account")
        
        # 🔒 НЕЛЬЗЯ УДАЛИТЬ СУПЕР-АДМИНА (ВООБЩЕ НИКОМУ)
        if admin.get('is_superuser'):
            raise HTTPException(status_code=403, detail="Cannot delete super admin account")
        
        # 🔒 STAFF АДМИН МОЖЕТ УДАЛЯТЬ ТОЛЬКО ОБЫЧНЫХ АДМИНОВ (не staff)
        if current_user.get('is_staff', False) and not current_user.get('is_superuser', False):
            if admin.get('is_staff'):
                raise HTTPException(status_code=403, detail="Staff admins can only delete regular admins")
        
        # ✅ УДАЛЕНИЕ РАЗРЕШЕНО
        await db.execute("DELETE FROM admins WHERE id = %s", (admin_id,))
        
        return RedirectResponse(url="/admin/list", status_code=303)
        
    except HTTPException:
        raise
    
    except Exception as e:
        return templates.TemplateResponse(
            "admin/admin_list.html", 
            {
                "request": request,
                "user": current_user,
                "error": f"Error deleting admin: {str(e)}"
            }
        )




@router.get("/edit/{admin_id}")
async def edit_admin_page(
    request: Request,
    admin_id: int,
):
    
    current_user = request.state.user
    current_user_id = current_user.get('sub')  # sub содержит ID пользователя

    """Страница редактирования админа"""
    if not current_user.get('is_staff', False):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    admin = await db.fetch_one("SELECT * FROM admins WHERE id = %s", (admin_id,))
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    
    # 🔥 ПРОВЕРКА: нельзя редактировать суперадмина (кроме самого себя)
    if admin['is_superuser']:
        raise HTTPException(status_code=403, detail="Cannot edit super admin accounts")
    
    # 🔥 STAFF АДМИН МОЖЕТ РЕДАКТИРОВАТЬ ТОЛЬКО ОБЫЧНЫХ АДМИНОВ
    if not current_user.get('is_superuser', False):  # Если НЕ суперадмин
        if admin['is_staff']:  # И пытается редактировать staff админа
            raise HTTPException(status_code=403, detail="Staff admins can only edit regular admins")
        if admin_id == current_user_id:  # И пытается редактировать себя
            raise HTTPException(status_code=403, detail="Cannot edit your own account")
    
    return templates.TemplateResponse(
        "admin/edit_admin.html", 
        {
            "request": request,
            "user": current_user,
            "admin": admin
        }
    )




@router.post("/edit/{admin_id}")
async def edit_admin(
    request: Request,
    admin_id: int,
    password: str = Form(None),
    is_staff: bool = Form(False),
):
    current_user = request.state.user
    current_user_id = current_user.get('sub')
    
    if not current_user.get('is_staff', False):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    try:
        # 🔥 ИСПОЛЬЗУЕМ НОВЫЙ ТРАНЗАКЦИОННЫЙ МЕТОД
        async with db.transaction() as cursor:
            # 🔒 БЛОКИРУЕМ АДМИНА НА ЗАПИСЬ
            await cursor.execute(
                "SELECT * FROM admins WHERE id = %s FOR UPDATE", 
                (admin_id,)
            )
            admin = await cursor.fetchone()
            
            if not admin:
                raise HTTPException(status_code=404, detail="Admin not found")
            
            # 🔒 ЗАПРЕЩАЕМ РЕДАКТИРОВАТЬ СУПЕР-АДМИНА
            if admin.get('is_superuser'):
                raise HTTPException(status_code=403, detail="Нельзя редактировать супер-администратора")
            
            # 🔒 STAFF НЕ МОЖЕТ ДЕЛАТЬ ДРУГИХ STAFF
            if current_user.get('is_staff', False) and not current_user.get('is_superuser', False):
                if is_staff:
                    raise HTTPException(status_code=403, detail="Staff админ не может создавать других Staff админов")
            
            # Проверки прав доступа
            if not current_user.get('is_superuser', False):
                if admin['is_staff']:
                    raise HTTPException(status_code=403, detail="Staff admins can only edit regular admins")
                if admin_id == current_user_id:
                    raise HTTPException(status_code=403, detail="Cannot edit your own account")
            
            can_edit_staff = current_user.get('is_superuser', False)
            
            # 🔧 ОБНОВЛЕНИЕ ДАННЫХ
            if password:
                password_hash = generate_password_hash(password)
                
                if can_edit_staff:
                    await cursor.execute(
                        "UPDATE admins SET password_hash = %s, is_staff = %s WHERE id = %s",
                        (password_hash, is_staff, admin_id)
                    )
                    print(f"✅ Updated password and is_staff for admin {admin_id}")
                else:
                    await cursor.execute(
                        "UPDATE admins SET password_hash = %s WHERE id = %s",
                        (password_hash, admin_id)
                    )
                    print(f"✅ Updated password for admin {admin_id}")
                    
            else:
                if can_edit_staff and (is_staff != admin['is_staff']):
                    await cursor.execute(
                        "UPDATE admins SET is_staff = %s WHERE id = %s",
                        (is_staff, admin_id)
                    )
                    print(f"✅ Updated is_staff to {is_staff} for admin {admin_id}")
        
        return RedirectResponse(url="/admin/list", status_code=303)
        
    except HTTPException:
        raise
    
    except Exception as e:
        admin = await db.fetch_one("SELECT * FROM admins WHERE id = %s", (admin_id,))
        return templates.TemplateResponse(
            "admin/edit_admin.html", 
            {
                "request": request,
                "user": current_user,
                "admin": admin,
                "error": f"Error updating admin: {str(e)}"
            }
        )

  
        
