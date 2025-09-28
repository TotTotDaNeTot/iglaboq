from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv

import logging
import os
import smtplib



logger = logging.getLogger(__name__)

load_dotenv()




class EmailService:
    def __init__(self):
        self.host = os.getenv('EMAIL_HOST')
        self.port = int(os.getenv('EMAIL_PORT'))
        self.user = os.getenv('EMAIL_USER')
        self.password = os.getenv('EMAIL_PASSWORD')
        self.from_email = os.getenv('EMAIL_FROM', os.getenv('EMAIL_USER'))
        self.use_tls = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
        
        
        
    
    async def send_email(self, to_email: str, subject: str, html_content: str):
        """Общий метод для отправки email"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.from_email
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(html_content, 'html'))

            with smtplib.SMTP(self.host, self.port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.user, self.password)
                server.send_message(msg)
            
            return True
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False



    # ОТПРАВКА УВЕДОМЛЕНИЯ ОБ ОТПРАВКЕ ЖУРНАЛА
    async def send_shipping_email(self, order: dict, track_number: str):
        """Отправляет email с трек-номером через Gmail"""
        if not order.get('email'):
            logger.warning(f"No email for order {order['id']}")
            return False

        try:
            # Проверка наличия обязательных данных
            if not all([self.user, self.password, self.from_email]):
                logger.error("Missing email credentials")
                return False

            # Создаем сообщение
            msg = MIMEMultipart()
            msg['From'] = self.from_email
            msg['To'] = order['email']
            msg['Subject'] = f"Ваш заказ #{order['id']} отправлен"

            html = f"""
            <html>
                <body>
                    <h2>Ваш заказ #{order['id']} был отправлен!</h2>
                    <p><strong>Трек-номер:</strong> {track_number}</p>
                    <p><strong>Адрес доставки:</strong> {order['city']}, {order['postcode']}</p>
                    <p><strong>Контакты:</strong> {order['phone']}</p>
                    <p>Отследить посылку: <a href="https://www.pochta.ru/tracking#{track_number}">ссылка</a></p>
                    <p>Спасибо за покупку!</p>
                </body>
            </html>
            """

            msg.attach(MIMEText(html, 'html'))

            # Настройка SMTP с обработкой ошибок
            try:
                with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                    server.ehlo()
                    if self.use_tls:
                        server.starttls()
                        server.ehlo()
                    
                    # Аутентификация
                    server.login(self.user, self.password)
                    
                    # Отправка письма
                    server.sendmail(self.from_email, order['email'], msg.as_string())
                
                logger.info(f"Email sent to {order['email']}")
                return True
            except smtplib.SMTPAuthenticationError as auth_error:
                logger.error(f"SMTP Authentication Error: {auth_error}")
                return False
            except Exception as smtp_error:
                logger.error(f"SMTP Error: {smtp_error}")
                return False

        except Exception as e:
            logger.error(f"Email sending error: {e}")
            return False
        
        
        
    
    # ОТПРАВКА УВЕДОМЛЕНИЯ О ПОКУПКЕ ЖУРНАЛА 
    async def send_order_confirmation(self, payment_id: str, amount: float, product_id: int, metadata: dict) -> bool:
        """Отправляет подтверждение заказа на email"""
        try:
            customer_email = metadata.get('email')
            if not customer_email:
                logger.warning(f"No email for payment {payment_id}")
                return False

            subject = f"Подтверждение заказа #{payment_id}"
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                    <h2 style="color: #333;">Спасибо за ваш заказ!</h2>
                    
                    <div style="background: #f9f9f9; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="color: #555;">Детали заказа:</h3>
                        <p><strong>Номер заказа:</strong> {payment_id}</p>
                        <p><strong>Сумма:</strong> {amount:.2f} RUB</p>
                        <p><strong>Товар:</strong> Журнал #{product_id}</p>
                    </div>
                    
                    <div style="background: #f0f8ff; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="color: #555;">Данные доставки:</h3>
                        <p><strong>ФИО:</strong> {metadata.get('fullname', '')}</p>
                        <p><strong>Телефон:</strong> {metadata.get('phone', '')}</p>
                        <p><strong>Город:</strong> {metadata.get('city', '')}</p>
                        <p><strong>Индекс:</strong> {metadata.get('postcode', '')}</p>
                        <p><strong>Email:</strong> {customer_email}</p>
                    </div>
                    
                    <p>Мы свяжемся с вами для уточнения деталей доставки.</p>
                    <p>С уважением,<br>Команда магазина</p>
                </body>
            </html>
            """
            
            return await self.send_email(customer_email, subject, html_content)
            
        except Exception as e:
            logger.error(f"Order confirmation email failed: {str(e)}")
            return False
        
        
        
    
    # ОТПРАВКА УВЕДОМЛЕНИЯ ОБ ОБНОВЛЕНИИ ТРЕК-НОМЕРА    
    async def send_tracking_update(self, order: dict, old_tracking: str, new_tracking: str) -> bool:
        """Отправляет email об изменении трек-номера"""
        try:
            if not order.get('email'):
                logger.warning(f"No email for order {order.get('id')}")
                return False

            subject = f"Изменение трек-номера (заказ #{order['id']})"
            html = f"""
            <html>
                <body style="font-family: Arial, sans-serif;">
                    <h2 style="color: #333;">Изменение трек-номера</h2>
                    <p>Ваш заказ <strong>#{order['id']}</strong> был обновлен:</p>
                    <table>
                        <tr><td><strong>Старый трек:</strong></td><td>{old_tracking or 'не указан'}</td></tr>
                        <tr><td><strong>Новый трек:</strong></td><td>{new_tracking}</td></tr>
                    </table>
                    <p>Отследить посылку: <a href="https://www.pochta.ru/tracking#{new_tracking}">Почта России</a></p>
                </body>
            </html>
            """
            
            return await self.send_email(
                to_email=order['email'],
                subject=subject,
                html_content=html
            )

        except Exception as e:
            logger.error(f"Email sending failed: {str(e)}")
            return False
    
    

email_service = EmailService()