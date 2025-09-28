from functools import wraps
from flask import request, current_app, redirect, url_for, jsonify

import jwt




def jwt_required(f):
    """Декоратор для JWT аутентификации"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 🔥 ПРОВЕРЯЕМ, УЖЕ ЛИ ПРОШЛА АУТЕНТИФИКАЦИЯ В MIDDLEWARE
        if hasattr(request, 'jwt_user') and request.jwt_user:
            # Middleware уже проверил - пропускаем
            return f(*args, **kwargs)
        
        # Если middleware не сработал - проверяем сами
        token = request.cookies.get('jwt_token')
        
        if not token:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required'}), 401
            else:
                return redirect(url_for('web_auth.web_login'))
        
        try:
            payload = jwt.decode(
                token, 
                current_app.secret_key,
                algorithms=['HS256'],
                options={"verify_exp": True}
            )
            request.jwt_user = payload
        except Exception as e:
            print(f"JWT verification failed: {e}")
            response = redirect(url_for('web_auth.web_login'))
            response.set_cookie('jwt_token', '', expires=0)
            return response
        
        return f(*args, **kwargs)
    return decorated_function



# # JWT required декоратор
# def jwt_required(f):
#     """Декоратор для JWT аутентификации (универсальный)"""
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         # Токен уже проверен в before_request, просто проверяем его наличие
#         if not hasattr(request, 'jwt_user'):
#             if request.path.startswith('/api/'):
#                 return jsonify({'error': 'Authentication required'}), 401
#             else:
#                 return redirect(url_for('login'))
#         return f(*args, **kwargs)
#     return decorated_function