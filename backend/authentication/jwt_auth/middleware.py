from flask import request, redirect, url_for, jsonify

from .token_utils import verify_jwt_token




def check_jwt_authentication():
    """Проверяем JWT аутентификацию для всех запросов"""
    print(f"🔍 Checking: {request.method} {request.path} (endpoint: {request.endpoint})")
    # Пропускаем публичные endpoints
    public_endpoints = ['web_auth.web_login', 'auth.api_login', 'static', 'api_auth_login']
    public_paths = ['/api/auth/login', '/login', '/web_auth/login']
    
    if request.endpoint in public_endpoints or request.path in public_paths:
        print(f"✅ Skipping auth for: {request.endpoint or request.path}")
        return
    
    # Пробуем получить токен из cookie
    token = request.cookies.get('jwt_token')
    print(f"🍪 JWT Cookie: {token}")
    
    if not token:
        print("❌ No JWT token in cookie")
        if request.path.startswith('/api/'):
            response = jsonify({'error': 'Authentication required'})
            response.status_code = 401
            return response
        else:
            return redirect(url_for('web_auth.web_login'))
    
    # Проверяем токен
    payload = verify_jwt_token(token)
    if not payload:
        print("❌ Invalid JWT token")
        if request.path.startswith('/api/'):
            response = jsonify({'error': 'Invalid token'})
            response.status_code = 401
            response.set_cookie('jwt_token', '', expires=0, path='/', domain='localhost')
            return response
        else:
            response = redirect(url_for('web_auth.web_login'))
            response.set_cookie('jwt_token', '', expires=0, path='/', domain='localhost')
            return response
    
    # Сохраняем данные пользователя
    request.jwt_user = payload
    print(f"✅ Authenticated user: {payload['username']} (is_admin: {payload.get('is_admin', False)})") 