from fastapi import APIRouter, Depends, HTTPException, Request, Form, Response
from fastapi.responses import JSONResponse

from authentication.jwt_auth.token_utils import create_jwt_token, verify_jwt_token, get_current_user

from werkzeug.security import check_password_hash

import os



router = APIRouter(prefix="/api/auth", tags=["auth"])

db = None




@router.post("/login")
async def api_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    """API endpoint для JWT аутентификации"""
    try:
        print(f"🔐 Login attempt for username: {username}")
        
        if db.pool is None:
            print("❌ Database not connected")
            raise HTTPException(status_code=500, detail="Database not connected")
        
        # Асинхронный запрос к БД
        admin = await db.fetch_one("SELECT * FROM admins WHERE username = %s", (username,))
        
        if admin:
            print(f"✅ Admin found: {admin['username']} (ID: {admin['id']})")
            print(f"🔒 Hash format: {admin['password_hash'][:50]}...")
            
            # Проверяем пароль
            password_valid = check_password_hash(admin['password_hash'], password)
            
            if password_valid:
                print("✅ Password verified successfully!")
                
                jwt_token = create_jwt_token(
                    user_id=admin['id'],
                    username=admin['username'],
                    is_staff=admin.get('is_staff', False),
                    is_superuser=admin.get('is_superuser', False),
                    is_admin=admin.get('is_admin', False)
                )
                
                print(f"🎫 JWT Token created: {jwt_token[:50]}...")
                
                # Устанавливаем cookie
                response = JSONResponse({
                    'success': True,
                    'token': jwt_token,
                    'redirect': f'/admin/dashboard?token={jwt_token}',
                    'user': {
                        'id': admin['id'],
                        'username': admin['username'],
                        'is_staff': admin.get('is_staff', False),
                        'is_superuser': admin.get('is_superuser', False),
                        'is_admin': admin.get('is_admin', False)
                    }
                })
                
                response.set_cookie(
                    key="jwt_token",
                    value=jwt_token,
                    httponly=True,
                    secure=False,
                    samesite="Lax",
                    max_age=24*60*60,
                    path="/",           # ВАЖНО: для всех путей
                    domain=None,        # Для всех доменов
                )
                
                print("✅ Login successful, cookie set")
                return response
            else:
                print("❌ Invalid password")
                raise HTTPException(status_code=401, detail="Invalid credentials")
                
        else:
            print("❌ Admin not found")
            raise HTTPException(status_code=401, detail="Invalid credentials")
            
    except HTTPException:
        # Перебрасываем HTTPException как есть
        print("⚠️ HTTPException raised, re-raising")
        raise
        
    except Exception as e:
        print(f"❌ Server error during login: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
    
    

@router.get("/me")
async def api_get_current_user(current_user: dict = Depends(get_current_user)):
    """Получить текущего пользователя по JWT"""
    return {"user": current_user}

@router.post("/refresh")
async def api_refresh_token(current_user: dict = Depends(get_current_user)):
    """Обновить JWT токен"""
    new_token = create_jwt_token(
        user_id=current_user['id'],
        username=current_user['username'],
        is_staff=current_user.get('is_staff', False),
        is_superuser=current_user.get('is_superuser', False)
    )
    
    return {"success": True, "token": new_token}

@router.post("/logout")
async def api_logout():
    """Выход из системы с очисткой cookie"""
    response = JSONResponse({"success": True})
    response.delete_cookie("jwt_token")
    return response


