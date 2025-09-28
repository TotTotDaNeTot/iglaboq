from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from werkzeug.security import check_password_hash
from authentication.jwt_auth.token_utils import create_jwt_token


router = APIRouter(prefix="/web_auth", tags=["web_auth"])

templates: Jinja2Templates = None
db = None 




@router.get("/login")
async def web_login_form(request: Request, message: str = None):
    return templates.TemplateResponse(
        "auth/login.html", 
        {
            "request": request,
            "message": {"text": message, "type": "error"} if message else None
        }
    )


@router.post("/login")
async def web_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    """Web login handler"""
    print(f"🔍 Method: POST")
    print(f"🔍 Form data: username={username}")
    print(f"🔍 Headers: {dict(request.headers)}")
    
    admin = await db.fetch_one("SELECT * FROM admins WHERE username = %s", (username,))
    
    if admin and check_password_hash(admin['password_hash'], password):
        jwt_token = create_jwt_token(
            user_id=admin['id'],
            username=admin['username'],
            is_staff=admin.get('is_staff', False),
            is_superuser=admin.get('is_superuser', False),
            is_admin=admin.get('is_admin', False)
        )
        
        print(f"✅ Created JWT token: {jwt_token}")
        
        # Для API запросов возвращаем токен, для web - редирект
        content_type = request.headers.get('content-type', '')
        if 'application/json' in content_type:
            return JSONResponse({
                'success': True,
                'token': jwt_token,
                'user': {
                    'id': admin['id'],
                    'username': admin['username'],
                    'is_staff': admin.get('is_staff', False),
                    'is_superuser': admin.get('is_superuser', False),
                    'is_admin': admin.get('is_admin', False)
                }
            })
        else:
            # Сохраняем токен в cookie для web и делаем редирект
            response = RedirectResponse(url="/admin/dashboard", status_code=303)
            response.set_cookie(
                key="jwt_token",
                value=jwt_token,
                httponly=True,
                secure=False,  # False для localhost
                samesite="Lax",
                path="/",
                max_age=24*60*60
            )
            
            print(f"✅ Setting cookie: {jwt_token[:50]}...")
            print(f"✅ Response headers: {dict(response.headers)}")
            return response
    
    # Если аутентификация не удалась
    if 'application/json' in request.headers.get('content-type', ''):
        return JSONResponse(
            {'success': False, 'message': 'Неверные учетные данные'}, 
            status_code=401
        )
    else:
        response = RedirectResponse(url="/web_auth/login?error=invalid", status_code=303)
        return response



@router.get("/logout")
async def logout():
    """Web logout"""
    response = RedirectResponse(url="/web_auth/login", status_code=303)
    response.delete_cookie("jwt_token")
    # Удаляем другие cookies если нужно
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    
    # Для передачи сообщения можно использовать query параметры или сессии
    return response



