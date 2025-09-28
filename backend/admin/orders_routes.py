from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, List

from authentication.jwt_auth.decorators import jwt_required
from backend.services.bot_notifications import send_delivery_update_notification, send_tracking_update_notification

from backend.services.email_service import EmailService

import logging




router = APIRouter(prefix="/orders", tags=["orders"])

templates: Jinja2Templates = None
bot = None
db = None

email_service = EmailService() 

logger = logging.getLogger(__name__)




@router.get("/details/{order_id}")
async def order_details(
    request: Request,
    order_id: int,
):
    
    current_user = request.state.user
    
    # Доступ имеют: обычные админы, staff и супер-админы
    has_access = current_user.get('is_admin', False) or current_user.get('is_staff', False)
    if not has_access:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    order = await db.fetch_one(
        """SELECT o.*, j.title as journal_title 
        FROM orders o 
        LEFT JOIN journals j ON o.product_id = j.id 
        WHERE o.id = %s""", 
        (order_id,)
    )
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return templates.TemplateResponse(
        'zakazy/order_details.html',
        {"request": request, "order": order, "user": current_user}
    )
    


@router.get("/list/{status}")
async def orders_list(
    request: Request, 
    status: str, 
):
    
    current_user = request.state.user
    
    # Доступ имеют: обычные админы, staff и супер-админы
    has_access = current_user.get('is_admin', False) or current_user.get('is_staff', False)
    if not has_access:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    status_titles = {
        'paid': 'New Paid Orders',
        'processing': 'Orders in Processing',
        'shipped': 'Shipped Orders',
        'cancelled': 'Cancelled Orders'
    }

    
    orders = await db.fetch_all(
        "SELECT * FROM orders WHERE status = %s ORDER BY created_at DESC",
        (status,)
    )
    
    return templates.TemplateResponse(
        'zakazy/orders_list.html',
        {
            "request": request,
            "orders": orders,
            "status": status,
            "status_title": status_titles.get(status),
            "user": current_user
        }
    )



@router.get("/update-status/{order_id}/{new_status}")
async def update_order_status(
    request: Request,
    order_id: int,
    new_status: str,
):
    
    current_user = request.state.user
    
    # Доступ имеют: обычные админы, staff и супер-админы
    has_access = current_user.get('is_admin', False) or current_user.get('is_staff', False)
    if not has_access:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    valid_statuses = ['processing', 'shipped', 'cancelled']
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    try:
        await db.execute(
            "UPDATE orders SET status = %s WHERE id = %s",
            (new_status, order_id)
        )
        return RedirectResponse(url=f"/orders/list/{new_status}", status_code=303)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")





@router.post("/ship")
async def ship_order(
    request: Request,
):
    current_user = request.state.user
    
    # Доступ имеют: обычные админы, staff и супер-админы
    has_access = current_user.get('is_admin', False) or current_user.get('is_staff', False)
    if not has_access:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    try:
        data = await request.json()
        order_id = data.get('order_id')
        track_number = data.get('track_number')
        
        if not order_id or not track_number:
            return JSONResponse(
                {'success': False, 'message': 'Заполните все поля'}, 
                status_code=400
            )

        # 🔥 ВСЕ ОПЕРАЦИИ БД В ОДНОЙ ТРАНЗАКЦИИ
        async with db.transaction() as cursor:
            # 1. 🔒 БЛОКИРУЕМ ЗАКАЗ ДЛЯ ОБНОВЛЕНИЯ
            await cursor.execute(
                "SELECT * FROM orders WHERE id = %s FOR UPDATE", 
                (order_id,)
            )
            order = await cursor.fetchone()

            if not order:
                return JSONResponse(
                    {'success': False, 'message': 'Заказ не найден'}, 
                    status_code=404
                )

            # 2. ОБНОВЛЯЕМ СТАТУС ЗАКАЗА
            await cursor.execute(
                "UPDATE orders SET status = 'shipped', track_number = %s WHERE id = %s",
                (track_number, order_id)
            )
            print(f"✅ Order {order_id} marked as shipped with tracking: {track_number}")


        # 🔥 УВЕДОМЛЕНИЯ ВНЕ ТРАНЗАКЦИИ (они могут падать, но это не должно влиять на статус заказа)
        telegram_sent = False
        email_sent = False
        
        # Telegram уведомление
        from backend.services.bot_notifications import send_telegram_notification
        
        if bot and hasattr(bot, 'send_message'):
            try:
                telegram_sent = await send_telegram_notification(bot, order, track_number)
                print(f"✅ Telegram notification sent: {telegram_sent}")
            except Exception as tg_error:
                print(f"❌ Telegram notification failed: {tg_error}")
                telegram_sent = False
        else:
            print("❌ Bot is invalid or has no send_message")
            telegram_sent = False
        
        # Email уведомление
        if order.get('email'):
            try:
                print(f"🔍 Email service: {email_service}")
                if hasattr(email_service, 'send_shipping_email'):
                    email_sent = await email_service.send_shipping_email(order, track_number)
                    print(f"✅ Email notification sent: {email_sent}")
                else:
                    logger.error("❌ send_shipping_email method not found!")
                    email_sent = False
            except Exception as email_error:
                logger.error(f"Ошибка отправки email: {email_error}")
                email_sent = False

        return JSONResponse({
            'success': True,
            'notifications': {
                'telegram': telegram_sent,
                'email': email_sent
            }
        })

    except Exception as e:
        logger.error(f"Ошибка в ship_order: {e}", exc_info=True)
        return JSONResponse(
            {'success': False, 'message': 'Ошибка сервера'}, 
            status_code=500
        )



@router.get("/api/orders")
async def orders_api(request: Request,):
    orders = await db.fetch_all("SELECT * FROM orders ORDER BY created_at DESC LIMIT 100")
    return JSONResponse(orders)



####### DELIVERY #########
@router.get("/delivery/{order_id}")
async def update_delivery_info_form(
    request: Request,
    order_id: int,
):
    
    current_user = request.state.user
    
    # Доступ имеют: обычные админы, staff и супер-админы
    has_access = current_user.get('is_admin', False) or current_user.get('is_staff', False)
    if not has_access:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    order = await db.fetch_one(
        "SELECT * FROM orders WHERE id = %s",
        (order_id,)
    )
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return templates.TemplateResponse(
        'zakazy/update_delivery.html',
        {"request": request, "order": order, "user": current_user}
    )



@router.post("/{order_id}/update_delivery")
async def update_delivery_info(
    request: Request,
    order_id: int,
    fullname: str = Form(...),
    city: str = Form(...),
    postcode: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...)
):
    
    current_user = request.state.user
    
    # Доступ имеют: обычные админы, staff и супер-админы
    has_access = current_user.get('is_admin', False) or current_user.get('is_staff', False)
    if not has_access:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    try:
        new_data = {
            'fullname': fullname,
            'city': city, 
            'postcode': postcode,
            'phone': phone,
            'email': email
        }
        
        # 🔥 ВСЕ ОПЕРАЦИИ В ОДНОЙ ТРАНЗАКЦИИ
        async with db.transaction() as cursor:
            # 1. 🔒 БЛОКИРУЕМ ЗАКАЗ СРАЗУ ДЛЯ ЧТЕНИЯ/ЗАПИСИ
            await cursor.execute(
                "SELECT * FROM orders WHERE id = %s FOR UPDATE", 
                (order_id,)
            )
            order = await cursor.fetchone()
            
            if not order:
                raise HTTPException(status_code=404, detail="Order not found")
            
            # 2. ОБНОВЛЯЕМ ДАННЫЕ (под защитой блокировки)
            await cursor.execute(
                """UPDATE orders SET 
                fullname = %s, city = %s, postcode = %s, 
                phone = %s, email = %s WHERE id = %s""",
                (new_data['fullname'], new_data['city'], new_data['postcode'],
                 new_data['phone'], new_data['email'], order_id)
            )
            print(f"✅ Updated delivery info for order {order_id}")
        
        # 🔥 УВЕДОМЛЕНИЯ ВНЕ ТРАНЗАКЦИИ (они могут падать)
        notification_results = await send_delivery_update_notification(
            bot=bot,
            order_id=order_id,
            tg_user_id=order.get('tg_user_id'),
            email=order.get('email'),
            new_data=new_data
        )
        
        return RedirectResponse(url=f"/orders/details/{order_id}", status_code=303)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating delivery: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при обновлении: {str(e)}")



@router.post("/{order_id}/edit_tracking")
async def edit_tracking(
    request: Request,
    order_id: int,
):
    
    current_user = request.state.user
    
    # Доступ имеют: обычные админы, staff и супер-админы
    has_access = current_user.get('is_admin', False) or current_user.get('is_staff', False)
    if not has_access:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    try:
        data = await request.json()
        new_tracking = data.get('tracking', '').strip()
        
        if not new_tracking:
            return JSONResponse(
                {'success': False, 'message': 'Трек-номер не может быть пустым'}, 
                status_code=400
            )

        # 🔥 ВСЕ ОПЕРАЦИИ БД В ОДНОЙ ТРАНЗАКЦИИ
        async with db.transaction() as cursor:
            # 1. 🔒 БЛОКИРУЕМ ЗАКАЗ ДЛЯ ЧТЕНИЯ/ЗАПИСИ
            await cursor.execute(
                "SELECT id, email, tg_user_id, track_number FROM orders WHERE id = %s FOR UPDATE", 
                (order_id,)
            )
            order = await cursor.fetchone()
            
            if not order:
                return JSONResponse(
                    {'success': False, 'message': 'Заказ не найден'}, 
                    status_code=404
                )

            old_tracking = order.get('track_number', '')
            
            # 2. ОБНОВЛЯЕМ ТРЕК-НОМЕР (под защитой блокировки)
            await cursor.execute(
                "UPDATE orders SET track_number = %s WHERE id = %s",
                (new_tracking, order_id)
            )
            print(f"✅ Tracking number updated for order {order_id}: {old_tracking} -> {new_tracking}")

        # 🔥 УВЕДОМЛЕНИЯ ВНЕ ТРАНЗАКЦИИ
        order_data = {
            'id': order_id,
            'email': order.get('email'),
            'tg_user_id': order.get('tg_user_id')
        }
        
        notification_results = await send_tracking_update_notification(
            bot=bot,
            order_data=order_data,
            old_tracking=old_tracking,
            new_tracking=new_tracking
        )
        
        return JSONResponse({
            'success': True,
            'notifications': notification_results
        })
    
    except Exception as e:
        logger.error(f"Error in edit_tracking: {str(e)}")
        return JSONResponse({
            'success': False, 
            'message': 'Ошибка сервера'
        }, status_code=500)


