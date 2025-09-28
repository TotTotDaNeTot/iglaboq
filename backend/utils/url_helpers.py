def url_for(endpoint, **kwargs):
    url_map = {
        'admin.create_admin': '/admin/create',
        'admin.dashboard': '/admin/dashboard',
        'admin.admin_list': '/admin/list',
        'journal.journals_list': '/journal/list',
        'journal.add_journal': '/journal/add',
        'orders.orders_list': '/orders/paid',
        'web_auth.web_login': '/web_auth/login',
        'web_auth.logout': '/web_auth/logout',
    }
    
    url = url_map.get(endpoint, f'/{endpoint}')
    
    # Подставляем параметры если есть
    for key, value in kwargs.items():
        url = url.replace(f'{{{key}}}', str(value))
    
    return url