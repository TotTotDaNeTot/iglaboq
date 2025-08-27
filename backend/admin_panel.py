import os
import asyncio
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path
from datetime import datetime

from database import db

from bot_notifications import *

from main import bot  

from flask_wtf.csrf import CSRFProtect

import sys
import logging

# Настройка путей
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))


# Глобальная переменная для event loop
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

logger = logging.getLogger(__name__)

# Инициализация Flask
app = Flask(
    __name__,
    template_folder=str(BASE_DIR / 'frontend' / 'templates' / 'admin_dashboard'),
    static_folder=str(BASE_DIR / 'frontend' / 'static')
)
app.secret_key = os.getenv('ADMIN_SECRET_KEY')
app.config['TEMPLATES_AUTO_RELOAD'] = True

csrf = CSRFProtect(app)

# Инициализация Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class AdminUser(UserMixin):
    def __init__(self, id, username, is_staff=True, is_superuser=False):
        self.id = id
        self.username = username
        self.is_staff = is_staff
        self.is_superuser = is_superuser

    @classmethod
    def from_db(cls, admin_data):
        """Создает объект AdminUser из данных БД"""
        return cls(
            id=admin_data['id'],
            username=admin_data['username'],
            is_staff=admin_data.get('is_staff', True),
            is_superuser=admin_data.get('is_superuser', False)
        )

# Синхронные обертки для асинхронных функций
def run_async(coro):
    return loop.run_until_complete(coro)

# Инициализация базы данных при старте
try:
    run_async(db.connect(
        unix_socket='/Applications/MAMP/tmp/mysql/mysql.sock',
        user='root',
        password='root',
        db='tg_bot',
        port=8889
    ))
    
except Exception as e:
    print(f"Ошибка инициализации БД: {e}")
    exit(1)



@login_manager.user_loader
def load_user(user_id):
    admin = run_async(db.fetch_one("SELECT * FROM admins WHERE id = %s", (user_id,)))
    return AdminUser.from_db(admin) if admin else None



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        admin = run_async(db.fetch_one("SELECT * FROM admins WHERE username = %s", (username,)))
        
        if admin and check_password_hash(admin['password_hash'], password):
            user = AdminUser.from_db(admin)
            login_user(user)
            return redirect(url_for('dashboard'))
        
        flash('Неверные учетные данные', 'error')
    
    return render_template('admin/login.html')



@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))



@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('admin/dashboard.html')




########## ADMINNS ##########
@app.route('/admin/create', methods=['GET', 'POST'])
@login_required
def create_admin():
    if not current_user.is_staff:
        flash('Недостаточно прав', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        is_staff = bool(request.form.get('is_staff')) if current_user.is_superuser else False
        
        if not username or not password:
            flash('Username and password are required', 'error')
            return redirect(url_for('create_admin'))
        
        try:
            password_hash = generate_password_hash(password)
            run_async(db.execute(
                "INSERT INTO admins (username, password_hash, is_staff) VALUES (%s, %s, %s)",
                (username, password_hash, is_staff)
            ))
            flash('Admin created successfully', 'success')
            return redirect(url_for('admin_list'))
        except Exception as e:
            flash(f'Error creating admin: {str(e)}', 'error')
    
    return render_template('admin/create_admin.html')



@app.route('/admin/list')
@login_required
def admin_list():
    if not current_user.is_staff:
        flash('Недостаточно прав', 'error')
        return redirect(url_for('dashboard'))
    
    admins = run_async(db.fetch_all("SELECT id, username, is_staff, is_superuser FROM admins ORDER BY is_superuser DESC, username"))
    return render_template('admin/staff_list.html', admins=admins)



@app.route('/admin/edit/<int:admin_id>', methods=['GET', 'POST'])
@login_required
def edit_admin(admin_id):
    if not current_user.is_staff:
        flash('Недостаточно прав', 'error')
        return redirect(url_for('dashboard'))
    
    admin = run_async(db.fetch_one("SELECT * FROM admins WHERE id = %s", (admin_id,)))
    if not admin:
        flash('Admin not found', 'error')
        return redirect(url_for('admin_list'))
    
    if admin['is_superuser'] and not current_user.is_superuser:
        flash('Cannot edit super admin', 'error')
        return redirect(url_for('admin_list'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        is_staff = bool(request.form.get('is_staff')) if current_user.is_superuser else admin['is_staff']
        
        try:
            if password:
                password_hash = generate_password_hash(password)
                run_async(db.execute(
                    "UPDATE admins SET password_hash = %s, is_staff = %s WHERE id = %s",
                    (password_hash, is_staff, admin_id))
                )
            else:
                run_async(db.execute(
                    "UPDATE admins SET is_staff = %s WHERE id = %s",
                    (is_staff, admin_id))
                )
            flash('Admin updated successfully', 'success')
            return redirect(url_for('admin_list'))
        except Exception as e:
            flash(f'Error updating admin: {str(e)}', 'error')
    
    return render_template('admin/edit_admin.html', admin=admin)



@app.route('/admin/delete/<int:admin_id>', methods=['GET', 'POST'])
@login_required
def delete_admin(admin_id):
    if not current_user.is_staff:
        flash('Недостаточно прав', 'error')
        return redirect(url_for('dashboard'))
    
    admin = run_async(db.fetch_one("SELECT * FROM admins WHERE id = %s", (admin_id,)))
    if not admin:
        flash('Admin not found', 'error')
        return redirect(url_for('admin_list'))
    
    if admin['is_superuser']:
        flash('Cannot delete super admin', 'error')
        return redirect(url_for('admin_list'))
    
    if request.method == 'POST':
        try:
            run_async(db.execute("DELETE FROM admins WHERE id = %s", (admin_id,)))
            flash('Admin deleted successfully', 'success')
            return redirect(url_for('admin_list'))
        except Exception as e:
            flash(f'Error deleting admin: {str(e)}', 'error')
    
    return render_template('admin/delete_admin.html', admin=admin)




####### JOURNALS #######
# Journals Management Routes
@app.route('/journals/list')
@login_required
def journals_list():
    if not current_user.is_staff:
        flash('Недостаточно прав', 'error')
        return redirect(url_for('dashboard'))
    
    journals = run_async(db.fetch_all("""
        SELECT id, title, description, price, year, created_at 
        FROM journals ORDER BY year DESC, created_at DESC
    """))
    return render_template('journals/journals_list.html', journals=journals)



@app.route('/journals/add', methods=['GET', 'POST'])
@login_required
def add_journal():
    if not current_user.is_staff:
        flash('Недостаточно прав', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        journal_id = request.form.get('journal_id')
        title = request.form.get('title')
        description = request.form.get('description')
        price = float(request.form.get('price', 0))
        year = int(request.form.get('year', datetime.now().year))
        
        try:
            # Проверяем, существует ли уже журнал с таким ID
            existing = run_async(db.fetch_one(
                "SELECT 1 FROM journals WHERE id = %s", (journal_id,)
            ))
            if existing:
                flash('Journal with this ID already exists', 'error')
                return redirect(url_for('add_journal'))
            
            run_async(db.execute(
                """INSERT INTO journals 
                (id, title, description, price, year) 
                VALUES (%s, %s, %s, %s, %s)""",
                (journal_id, title, description, price, year)
            ))
            flash('Journal added successfully', 'success')
            return redirect(url_for('journals_list'))
        except Exception as e:
            flash(f'Error adding journal: {str(e)}', 'error')
    
    current_year = datetime.now().year
    return render_template('journals/add_journal.html', current_year=current_year)



@app.route('/journals/edit/<int:journal_id>', methods=['GET', 'POST'])
@login_required
def edit_journal(journal_id):
    
    if not current_user.is_staff:
        flash('Недостаточно прав', 'error')
        return redirect(url_for('dashboard'))
    
    journal = run_async(db.fetch_one("SELECT * FROM journals WHERE id = %s", (journal_id,)))
    if not journal:
        flash('Journal not found', 'error')
        return redirect(url_for('journals_list'))
    
    current_year = datetime.now().year
    
    if request.method == 'POST':
        new_id = request.form.get('journal_id')
        title = request.form.get('title')
        description = request.form.get('description')
        price = float(request.form.get('price', 0))
        year = int(request.form.get('year', datetime.now().year))
        
        try:
            if new_id and int(new_id) != journal_id:
                existing = run_async(db.fetch_one(
                    "SELECT id FROM journals WHERE id = %s", (new_id,)
                ))
                if existing:
                    flash('This journal ID is already taken!', 'error')
                    return redirect(url_for('edit_journal', journal_id=journal_id))
            
            run_async(db.execute(
                """UPDATE journals SET 
                id = %s, title = %s, description = %s, 
                price = %s, year = %s 
                WHERE id = %s""",
                (new_id or journal_id, title, description, price, year, journal_id)
            ))
            flash('Journal updated successfully', 'success')
            return redirect(url_for('journals_list'))
        except Exception as e:
            flash(f'Error updating journal: {str(e)}', 'error')
    
    # Убедитесь, что имя файла точно совпадает с существующим
    return render_template('journals/edit_journal.html', journal=journal, current_year=current_year)



@app.route('/journals/delete/<int:journal_id>', methods=['POST'])
@login_required
def delete_journal(journal_id):
    if not current_user.is_staff:
        flash('Недостаточно прав', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        run_async(db.execute("DELETE FROM journals WHERE id = %s", (journal_id,)))
        flash('Journal deleted successfully', 'success')
    except Exception as e:
        flash(f'Error deleting journal: {str(e)}', 'error')
    
    return redirect(url_for('journals_list'))



############.  ORDERS ###########

@app.route('/orders/<status>')
@login_required
def orders_list(status):
    if not current_user.is_staff:
        flash('Недостаточно прав', 'error')
        return redirect(url_for('dashboard'))
    
    status_titles = {
        'paid': 'New Paid Orders',
        'processing': 'Orders in Processing',
        'shipped': 'Shipped Orders',
        'cancelled': 'Cancelled Orders'
    }
    
    if status not in status_titles:
        status = 'paid'
    
    orders = run_async(db.fetch_all(
        "SELECT * FROM orders WHERE status = %s ORDER BY created_at DESC",
        (status,)
    ))
    
    return render_template(
        'asdasd/orders_list.html',
        orders=orders,
        status=status,
        status_title=status_titles.get(status)
    )
    
    
    
@app.route('/order/<int:order_id>/update/<new_status>')
@login_required
def update_order_status(order_id, new_status):
    if not current_user.is_staff:
        flash('Недостаточно прав', 'error')
        return redirect(url_for('dashboard'))
    
    valid_statuses = ['processing', 'shipped', 'cancelled']
    if new_status not in valid_statuses:
        flash('Invalid status', 'error')
        return redirect(url_for('orders_list', status='paid'))
    
    try:
        run_async(db.execute(
            "UPDATE orders SET status = %s WHERE id = %s",
            (new_status, order_id)
        ))
        flash('Order status updated', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('orders_list', status=new_status))



@app.route('/order/<int:order_id>')
@login_required
def order_details(order_id):
    order = run_async(db.fetch_one(
        """SELECT o.*, j.title as journal_title 
        FROM orders o 
        LEFT JOIN journals j ON o.product_id = j.id 
        WHERE o.id = %s""", 
        (order_id,)
    ))
    
    if not order:
        flash('Order not found', 'error')
        return redirect(url_for('orders_list', status='paid'))
    
    return render_template(
        'asdasd/order_details.html',
        order=order
    )
    
    
    
@app.route('/order/ship', methods=['POST'])
@login_required
def ship_order():
    if not current_user.is_staff:
        return jsonify({'success': False, 'message': 'Недостаточно прав'}), 403
    
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        track_number = data.get('track_number')
        
        if not order_id or not track_number:
            return jsonify({'success': False, 'message': 'Заполните все поля'}), 400

        # 1. Обновляем статус заказа
        run_async(db.execute(
            "UPDATE orders SET status = 'shipped', track_number = %s WHERE id = %s",
            (track_number, order_id)
        ))

        # 2. Получаем данные заказа
        order = run_async(db.fetch_one(
            "SELECT * FROM orders WHERE id = %s",
            (order_id,)
        ))

        if not order:
            return jsonify({'success': False, 'message': 'Заказ не найден'}), 404

        # 3. Отправляем уведомления
        from main import bot
        
        # Telegram уведомление (ваш оригинальный код)
        telegram_sent = run_async(send_telegram_notification(bot, order, track_number))
        
        # Email уведомление (ваш оригинальный код)
        email_sent = False
        if order.get('email'):
            try:
                email_sent = run_async(email_service.send_shipping_email(order, track_number))
                logger.info(f"Результат отправки email: {email_sent}")
            except Exception as e:
                logger.error(f"Ошибка отправки email: {e}")

        return jsonify({
            'success': True,
            'notifications': {
                'telegram': telegram_sent,
                'email': email_sent
            }
        })

    except Exception as e:
        logger.error(f"Ошибка в ship_order: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Ошибка сервера'}), 500
    

@app.route('/api/orders')
@login_required
def orders_api():
    orders = run_async(db.fetch_all("SELECT * FROM orders ORDER BY created_at DESC LIMIT 100"))
    return jsonify(orders)



####### DELIVERY #########
@app.route('/order/<int:order_id>/update_delivery', methods=['GET', 'POST'])
@login_required
def update_delivery_info(order_id):
    if not current_user.is_staff:
        flash('Недостаточно прав', 'error')
        return redirect(url_for('dashboard'))
    
    order = run_async(db.fetch_one(
        "SELECT * FROM orders WHERE id = %s",
        (order_id,)
    ))
    
    if not order:
        flash('Order not found', 'error')
        return redirect(url_for('orders_list', status='paid'))
    
    if request.method == 'POST':
        try:
            new_data = {
                'fullname': request.form.get('fullname'),
                'city': request.form.get('city'), 
                'postcode': request.form.get('postcode'),
                'phone': request.form.get('phone'),
                'email': request.form.get('email')
            }
            
            # Обновление в БД
            run_async(db.execute(
                """UPDATE orders SET 
                fullname = %s, city = %s, postcode = %s, 
                phone = %s, email = %s WHERE id = %s""",
                (new_data['fullname'], new_data['city'], new_data['postcode'],
                 new_data['phone'], new_data['email'], order_id)
            ))
            
            # Отправка уведомлений
            from main import bot
            notification_results = run_async(
                send_delivery_update_notification(
                    bot=bot,
                    order_id=order_id,
                    tg_user_id=order.get('tg_user_id'),
                    email=order.get('email'),
                    new_data=new_data
                )
            )
            
            flash('Данные доставки успешно обновлены!', 'success')
            return redirect(url_for('order_details', order_id=order_id))
            
        except Exception as e:
            logger.error(f"Error updating delivery: {str(e)}")
            flash(f'Ошибка при обновлении: {str(e)}', 'error')
    
    return render_template('asdasd/update_delivery.html', order=order)




@app.route('/order/<int:order_id>/edit_tracking', methods=['POST'])
@login_required
def edit_tracking(order_id):
    try:
        data = request.get_json()
        new_tracking = data.get('tracking', '').strip()
        
        if not new_tracking:
            return jsonify({'success': False, 'message': 'Трек-номер не может быть пустым'}), 400

        # Получаем текущие данные заказа
        order = run_async(db.fetch_one(
            "SELECT id, email, tg_user_id, track_number FROM orders WHERE id = %s",
            (order_id,)
        ))
        
        if not order:
            return jsonify({'success': False, 'message': 'Заказ не найден'}), 404

        old_tracking = order.get('track_number', '')
        
        # Обновляем трек-номер в базе
        run_async(db.execute(
            "UPDATE orders SET track_number = %s WHERE id = %s",
            (new_tracking, order_id)
        ))
        
        # Подготавливаем данные для уведомления
        order_data = {
            'id': order_id,
            'email': order.get('email'),
            'tg_user_id': order.get('tg_user_id')
        }
        
        # Отправляем уведомления через run_async
        from main import bot
        notification_results = run_async(
            send_tracking_update_notification(
                bot=bot,
                order_data=order_data,
                old_tracking=old_tracking,
                new_tracking=new_tracking
            )
        )
        
        return jsonify({
            'success': True,
            'notifications': notification_results
        })
    
    except Exception as e:
        logger.error(f"Error in edit_tracking: {str(e)}")
        return jsonify({
            'success': False, 
            'message': 'Ошибка сервера'
        }), 500
    



        


if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5006, debug=True)
    finally:
        # Закрытие соединений при завершении
        run_async(db.close())