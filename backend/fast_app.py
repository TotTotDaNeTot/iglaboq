import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import JSONResponse, HTMLResponse

from pydantic import BaseModel

from backend.database import db



# Настройка путей
sys.path.append('/Users/kirill/Desktop/testBot')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))






from bot_main import bot


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting up...")
    await db.connect()
    print("✅ Database connected")
    
    # ⭐⭐⭐ УСТАНАВЛИВАЕМ DB ДЛЯ ВСЕХ МОДУЛЕЙ ⭐⭐⭐
    from authentication.jwt_auth import token_utils
    token_utils.db = db
     
    from authentication.web_auth import routes
    routes.db = db
    
    from authentication.auth import routes
    routes.db = db
    
    from admin import admin_routes
    admin_routes.db = db
    
    from admin import journal_routes  
    journal_routes.db = db
    
    from admin import orders_routes
    orders_routes.db = db
    orders_routes.bot = bot
    
    from admin import bot_routes
    bot_routes.db = db
    
    from backend.services import bot_notifications
    bot_notifications.db = db
    
    from backend.services import email_service
    email_service.db = db  
    
    
    from authentication.auth.routes import router as auth_router
    from authentication.web_auth.routes import router as web_auth_router
    from admin.admin_routes import router as admin_router
    from admin.journal_routes import router as journal_router
    from admin.orders_routes import router as orders_router
    from admin.bot_routes import router as bot_router

    # Регистрируем роутеры
    app.include_router(auth_router)
    app.include_router(web_auth_router)
    app.include_router(journal_router)
    app.include_router(admin_router, prefix="/admin")
    app.include_router(orders_router)
    app.include_router(bot_router)
    
    # Устанавливаем templates для всех модулей
    import admin.admin_routes
    admin.admin_routes.templates = templates

    import authentication.web_auth.routes  
    authentication.web_auth.routes.templates = templates

    import admin.journal_routes
    admin.journal_routes.templates = templates

    import admin.orders_routes
    admin.orders_routes.templates = templates
    
    yield  # Здесь приложение работает
    
    # Shutdown  
    print("🛑 Shutting down...")
    await db.close()
    print("✅ Database disconnected")
    



# Инициализация FastAPI с lifespan
app = FastAPI(
    title="Admin Panel", 
    version="1.0.0",
    lifespan=lifespan  # ← ПЕРЕДАЕМ LIFESPAN ЗДЕСЬ
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5006"],  # явный origin
    allow_credentials=True,  # разрешить куки
    allow_methods=["*"],
    allow_headers=["*"],
)

# Статические файлы и шаблоны
frontend_static_dir = BASE_DIR / "frontend" / "static"
frontend_templates_dir = BASE_DIR / "frontend" / "templates" / "admin_dashboard"

# Проверяем и создаем директории если нужно
frontend_static_dir.mkdir(parents=True, exist_ok=True)
frontend_templates_dir.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(frontend_static_dir)), name="static")
templates = Jinja2Templates(directory=str(frontend_templates_dir))





# JWT
SECRET_KEY = os.getenv("ADMIN_SECRET_KEY")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Модели
class LoginRequest(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str




from fastapi import Request
from authentication.jwt_auth.token_utils import verify_jwt_token
from fastapi.responses import RedirectResponse

@app.middleware("http")
async def jwt_middleware(request: Request, call_next):
    # Пропускаем публичные эндпоинты
    if request.url.path in ["/", "/web_auth/login", "/api/auth/login", "/health", "/debug-token"]:
        return await call_next(request)
    
    # Проверяем JWT токен из cookie
    jwt_token = request.cookies.get("jwt_token")
    print(f"🍪 JWT Middleware: token from cookie = {jwt_token}")
    
    if not jwt_token:
        print("❌ No JWT token found in cookies")
        return RedirectResponse(url="/web_auth/login", status_code=303)
    
    # Проверяем токен
    payload = await verify_jwt_token(jwt_token)
    if not payload:
        print("❌ JWT token verification failed")
        response = RedirectResponse(url="/web_auth/login", status_code=303)
        response.delete_cookie("jwt_token")
        return response
    
    print(f"✅ JWT token valid: {payload}")
    # Добавляем пользователя в request state для использования в эндпоинтах
    request.state.user = payload
    
    return await call_next(request)



# ⭐⭐⭐ ЭНДПОИНТ ДЛЯ ОТЛАДКИ ТОКЕНА ⭐⭐⭐
@app.get("/debug-token")
async def debug_token(request: Request):
    token = request.cookies.get("jwt_token")
    if not token:
        return {"error": "No token found in cookies"}
    
    try:
        import jwt
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return {
            "token": token[:50] + "..." if len(token) > 50 else token,
            "payload": payload, 
            "valid": True,
            "cookies": dict(request.cookies)
        }
    except Exception as e:
        return {
            "token": token[:50] + "..." if len(token) > 50 else token,
            "error": str(e), 
            "valid": False,
            "cookies": dict(request.cookies)
        }




@app.get("/debug-admins")
async def debug_admins():
    try:
        admins = await db.fetch_all("SELECT id, username, password_hash FROM admins")
        
        # Добавляем информацию о формате хэша
        for admin in admins:
            hash_str = admin['password_hash']
            if isinstance(hash_str, bytes):
                admin['hash_type'] = 'bytes'
                admin['hash_preview'] = hash_str[:20]  # первые 20 байт
            else:
                admin['hash_type'] = 'string' 
                admin['hash_preview'] = hash_str[:50]  # первые 50 символов
                admin['hash_length'] = len(hash_str)
                
        return {"admins": admins}
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}


@app.get("/debug-auth")
async def debug_auth(request: Request):
    return {
        "cookies": dict(request.cookies),
        "has_jwt": "jwt_token" in request.cookies,
        "jwt_token": request.cookies.get("jwt_token", "NOT_FOUND")[:50] + "..." if request.cookies.get("jwt_token") else None
    }
    


# Базовые роуты
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})

@app.get("/health")
async def health_check():
    return {"status": "ok", "database": "connected"}


# Простая замена Flask url_for
def url_for(endpoint, **kwargs):
    # Базовые mapping'и
    url_map = {
        'admin.create_admin': '/admin/create',
        'admin.dashboard': '/admin/dashboard',
        'orders.orders_list': '/orders/paid',
    }
    return url_map.get(endpoint, f'/{endpoint}')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.fast_app:app", host="0.0.0.0", port=5006, reload=True)
    