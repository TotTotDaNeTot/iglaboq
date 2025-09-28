from aiogram import Bot
from aiogram.types import InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton

from typing import Optional, Dict

from services.email_service import email_service
from database import db

import asyncio
import requests
import logging
import os
import aiohttp



logger = logging.getLogger(__name__)




def sync_send_shipping_notification(bot: Bot, order_id: int, track_number: str) -> Dict[str, bool]:
    """Синхронная обертка для send_shipping_notification"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            send_shipping_notification(bot, order_id, track_number)
        )
    finally:
        loop.close()



def sync_send_delivery_update_notification(
    bot: Bot,
    order_id: int,
    tg_user_id: Optional[int],
    email: Optional[str],
    new_data: dict
) -> Dict[str, bool]:
    """Синхронная обертка для send_delivery_update_notification"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            send_delivery_update_notification(
                bot, order_id, tg_user_id, email, new_data
            )
        )
    finally:
        loop.close()



async def send_shipping_notification(bot: Bot, order_id: int, track_number: str):
    """Отправляет уведомления о доставке"""
    try:
        order = await db.fetch_one(
            "SELECT * FROM orders WHERE id = %s",
            (order_id,)
        )
        
        if not order:
            logger.warning(f"Order {order_id} not found")
            return {'telegram': False, 'email': False}

        # Telegram уведомление
        telegram_sent = False
        if order.get('tg_user_id'):
            try:
                message = (
                    f"🚚 Ваш заказ #{order_id} отправлен!\n\n"
                    f"📦 Трек-номер: <b>{track_number}</b>\n"
                    f"📍 Адрес: {order['city']}, {order['postcode']}\n"
                    f"📞 Телефон: {order['phone']}\n\n"
                    f"🔍 Отследить: https://www.pochta.ru/tracking#{track_number}"
                )
                
                await bot.send_message(
                    chat_id=order['tg_user_id'],
                    text=message,
                    parse_mode='HTML'
                )
                telegram_sent = True
            except Exception as e:
                logger.error(f"Telegram error: {e}")

        # Email уведомление
        email_sent = False
        if order.get('email'):
            try:
                email_sent = await email_service.send_shipping_email(order, track_number)
            except Exception as e:
                logger.error(f"Email error: {e}")
        
        return {'telegram': telegram_sent, 'email': email_sent}
        
    except Exception as e:
        logger.error(f"Notification error: {e}")
        return {'telegram': False, 'email': False}



async def send_telegram_notification(bot: Bot, order: dict, track_number: str):
    """Отправляет Telegram уведомление"""
    if not order.get('tg_user_id'):
        logger.warning(f"No tg_user_id for order {order.get('id')}")
        return False


    try:
        journal = await db.fetch_one(
            "SELECT * FROM journals WHERE id = %s",
            (order['product_id'],)
        ) if order.get('product_id') else None

        message_text = (
            f"🚚 Ваш заказ #{order['id']} отправлен!\n\n"
            f"📦 Трек-номер: <b>{track_number}</b>\n"
            f"📍 Адрес: {order['city']}, {order['postcode']}\n"
            f"📞 Контакты: {order['phone']}\n\n"
        )
        
        if journal:
            message_text += (
                f"📖 Журнал: <b>{journal.get('title', '')}</b> ({journal.get('year', '')})\n"
                f"💳 Сумма: {order['amount']} {order['currency']}\n\n"
            )
        
        message_text += "Спасибо за покупку! ❤️"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="📦 Отследить посылку",
                url=f"https://www.pochta.ru/tracking#{track_number}"
            )
        ]])

        try:
            photo_url = f"https://raw.githubusercontent.com/TotTotDaNeTot/iglaboq/main/media/journals/igla_{order['product_id']}.jpg"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(photo_url, timeout=5) as response:
                    if response.status == 200:
                        await bot.send_photo(
                            chat_id=order['tg_user_id'],
                            photo=photo_url,
                            caption=message_text,
                            reply_markup=keyboard,
                            parse_mode='HTML'
                        )
                        return True
                        
        except Exception as photo_error:
            logger.warning(f"Photo send error: {photo_error}")

        await bot.send_message(
            chat_id=order['tg_user_id'],
            text=message_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return True
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False




async def send_delivery_update_notification(
    bot: Bot, 
    order_id: int,
    tg_user_id: Optional[int],
    email: Optional[str],
    new_data: dict
) -> Dict[str, bool]:
    """Улучшенная функция отправки уведомлений с повторными попытками"""
    results = {'telegram': False, 'email': False}
    
    try:
        message_text = (
            f"ℹ️ Данные доставки для заказа #{order_id} были обновлены:\n\n"
            f"👤 ФИО: {new_data['fullname']}\n"
            f"🏙️ Город: {new_data['city']}\n"
            f"📮 Индекс: {new_data['postcode']}\n"
            f"📞 Телефон: {new_data['phone']}\n"
            f"📧 Email: {new_data['email']}\n\n"
            f"Если вы не вносили эти изменения, свяжитесь с поддержкой."
        )

        # Telegram уведомление с 3 попытками
        if tg_user_id:
            for attempt in range(3):
                try:
                    await bot.send_message(
                        chat_id=tg_user_id,
                        text=message_text,
                        parse_mode='HTML'
                    )
                    results['telegram'] = True
                    break
                except Exception as e:
                    logger.error(f"Attempt {attempt + 1} failed for order {order_id}: {str(e)}")
                    if attempt < 2:  # Если это не последняя попытка
                        await asyncio.sleep(2)  # Ждем 2 секунды перед повторной попыткой

        # Email уведомление
        if email:
            try:
                subject = f"Изменение данных доставки заказа #{order_id}"
                html = render_email_template(new_data, order_id)
                results['email'] = await email_service.send_email(email, subject, html)
            except Exception as e:
                logger.error(f"Email sending failed for order {order_id}: {str(e)}")

    except Exception as e:
        logger.error(f"Unexpected error in notification for order {order_id}: {str(e)}", exc_info=True)
    
    return results





def render_email_template(new_data: dict, order_id: int) -> str:
    """Генерация HTML шаблона для email"""
    return f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6;">
            <h2 style="color: #2c3e50;">Изменение данных доставки</h2>
            <p>Данные доставки для вашего заказа <strong>#{order_id}</strong> были обновлены:</p>
            
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd; width: 30%;"><strong>ФИО:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{new_data['fullname']}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Город:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{new_data['city']}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Индекс:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{new_data['postcode']}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Телефон:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{new_data['phone']}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Email:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{new_data['email']}</td>
                </tr>
            </table>
            
            <p style="color: #7f8c8d;">Если вы не вносили эти изменения, пожалуйста, свяжитесь с поддержкой.</p>
        </body>
    </html>
    """



async def send_tracking_update_notification(
    bot: Bot,
    order_data: Dict,
    old_tracking: str,
    new_tracking: str
) -> Dict[str, bool]:
    """Отправка уведомления об изменении трек-номера"""
    results = {'telegram': False, 'email': False}
    
    try:
        # Telegram уведомление
        if order_data.get('tg_user_id'):
            try:
                message = (
                    f"✉️ Изменение трек-номера для заказа #{order_data['id']}\n\n"
                    f"📦 Старый трек: {old_tracking or 'не указан'}\n"
                    f"🆕 Новый трек: <b>{new_tracking}</b>\n\n"
                    f"🔍 Отследить: https://www.pochta.ru/tracking#{new_tracking}"
                )
                
                await bot.send_message(
                    chat_id=order_data['tg_user_id'],
                    text=message,
                    parse_mode='HTML'
                )
                results['telegram'] = True
                logger.info(f"Telegram notification sent to {order_data['tg_user_id']}")
            except Exception as e:
                logger.error(f"Telegram send error: {e}")

        # Email уведомление
        if order_data.get('email'):
            results['email'] = await email_service.send_tracking_update(
                order=order_data,
                old_tracking=old_tracking,
                new_tracking=new_tracking
            )
            
    except Exception as e:
        logger.error(f"Notification error: {e}")
    
    return results



async def send_telegram_payment_async(
    chat_id: int, 
    payment_id: str, 
    amount: float, 
    product_id: int, 
    customer_name: str = "", 
    delivery_city: str = "", 
    delivery_postcode: str = ""
) -> bool:
    """Асинхронно отправляет уведомление о заказе в Telegram"""
    import aiohttp
    try:
        bot_token = os.getenv('BOT_TOKEN')
        if not bot_token:
            logger.error("BOT_TOKEN environment variable not set")
            return False
            
        message = f"""
        🛍️ Новый оплаченный заказ
        
        🔹 Номер платежа: {payment_id}
        🔹 Сумма: {amount:.2f} RUB
        🔹 Товар: #{product_id}
        
        Данные доставки:
        👤 ФИО: {customer_name}
        🏙️ Город: {delivery_city}
        📮 Индекс: {delivery_postcode}
        """
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': int(chat_id),
            'text': message,
            'parse_mode': 'HTML'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                response_data = await response.json()
                
                if response.status == 200 and response_data.get('ok'):
                    logger.info(f"Notification sent to chat {chat_id}. Response: {response_data}")
                    return True
                else:
                    logger.error(f"Telegram API error: {response_data}")
                    return False
                
    except aiohttp.ClientError as e:
        logger.error(f"Telegram API request failed: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error sending Telegram notification: {str(e)}", exc_info=True)
        return False

