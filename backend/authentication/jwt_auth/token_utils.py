from fastapi import Depends, HTTPException, status, Request  
from fastapi.security import OAuth2PasswordBearer

import jwt
import os



SECRET_KEY = os.getenv("ADMIN_SECRET_KEY")

db = None 



def create_jwt_token(user_id: int, username: str, is_staff: bool = False, is_superuser: bool = False, is_admin: bool = False):
    """Создает JWT токен"""
    from datetime import datetime, timezone, timedelta
    payload = {
        'sub': str(user_id),
        'username': username,
        'is_staff': is_staff,
        'is_superuser': is_superuser,
        'is_admin': is_admin,
        'exp': datetime.now(timezone.utc) + timedelta(hours=24),
        'iat': datetime.now(timezone.utc)
    }
    
    token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')
    print(f"🎫 Created JWT token: {token}")
    print(f"   Payload: {payload}")
    print(f"   Secret key: {SECRET_KEY}")
    
    return token



async def verify_jwt_token(token: str):
    """Проверяет JWT токен"""
    try:
        print(f"🔐 Verifying token: {token[:50]}...")
        print(f"🔑 Using SECRET_KEY: {SECRET_KEY}")
        
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        
        if 'sub' in payload:
            payload['sub'] = int(payload['sub'])
        
        print(f"✅ Token verified successfully: {payload}")
        return payload
        
    except jwt.ExpiredSignatureError:
        print("❌ Token expired")
        return None
    except jwt.InvalidTokenError as e:
        print(f"❌ Invalid token: {e}")
        return None
    except Exception as e:
        print(f"❌ Token verification failed: {e}")
        import traceback
        traceback.print_exc()
        return None




async def get_current_user(request: Request):  # ← Принимаем Request вместо token
    if db is None or db.pool is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    try:
        # Получаем токен из cookies 
        jwt_token = request.cookies.get("jwt_token")
        print(f"🔍 Getting token from cookies: {jwt_token}")
        
        if not jwt_token:
            raise HTTPException(status_code=401, detail="No token provided")
        
        payload = jwt.decode(jwt_token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        
        print(f"✅ Token valid, user_id: {user_id}")
        
        # Получаем пользователя из БД
        user = await db.fetch_one("SELECT * FROM admins WHERE id = %s", (user_id,))
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
            
        return {
            "id": user["id"],
            "username": user["username"], 
            "is_staff": user.get("is_staff", False),
            "is_superuser": user.get("is_superuser", False)
        }
        
    except jwt.PyJWTError as e:
        print(f"❌ JWT Error in get_current_user: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        print(f"❌ Other error in get_current_user: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")


