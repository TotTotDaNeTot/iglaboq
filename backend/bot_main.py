from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import *
from aiogram.types import *
from aiogram import types, F
from aiogram.fsm.storage.memory import MemoryStorage

from dotenv import load_dotenv

from database import db 

from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware

from fastapi import FastAPI

import aiohttp
import os 
import json
import base64
import urllib
import time
import asyncio
import logging

import uvicorn



load_dotenv()


app = FastAPI()


bot = Bot(
    token=os.getenv('BOT_TOKEN'),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

storage = MemoryStorage()
dp = Dispatcher(bot=bot, storage=storage)


logger = logging.getLogger(__name__)



PROVIDER_TOKEN = os.getenv('PROVIDER_TOKEN')



# Глобальное хранилище для фото
photo_storage = {}



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Разрешаем все домены (для теста)
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.on_event("startup")
async def on_startup():
    try:
        
        await db.connect(
            unix_socket=os.getenv('DB_UNIX_SOCKET'),
            user=os.getenv('DB_USER'),
            password=os.getenv('PASSWORD'),
            db=os.getenv('DB_NAME'),
            port=os.getenv('DB_PORT')
        )
        logger.info("✅ Подключение к БД успешно установлено")
        
        # Проверка подключения
        test_result = await db.fetch_one("SELECT 1")
        logger.info(f"Тест запроса к БД: {test_result}")
        
        # Запуск бота в фоне
        asyncio.create_task(dp.start_polling(bot))
        logger.info("🤖 Бот запущен")
        
    except Exception as e:
        logger.critical(f"❌ Критическая ошибка подключения к БД: {e}")
        raise 
    
    
    

@dp.message(Command("start"))
async def start(message: types.Message):
    if not message.text.startswith('/start payment_success_'):
        
        main_kb = [
            [types.KeyboardButton(text="📚 Журналы")],
            [types.KeyboardButton(text="📝 Описание")],
            [types.KeyboardButton(text="📞 Контакты")]
        ]
        
        keyboard = types.ReplyKeyboardMarkup(
            keyboard=main_kb,
            resize_keyboard=True,
            input_field_placeholder="Выберите раздел"
        )
        
        await message.answer(
            "Добро пожаловать в официальный магазин журнала 'Игла'!",
            reply_markup=keyboard
        )
    
    
        
        

@dp.message(F.text == "📚 Журналы")
async def show_journals(message: types.Message):
    try:
        if not db.pool:
            await message.answer("⚠️ Нет подключения к БД")
            return
            
        journals = await db.get_all_journals()
        
        if not journals:
            await message.answer("📭 Журналы временно отсутствуют")
            return

        kb = types.InlineKeyboardMarkup(inline_keyboard=[])
        
        for journal in journals:
            kb.inline_keyboard.append([
                types.InlineKeyboardButton(
                    text=f"{journal['title']} ({journal['year']}) - {journal['price']}₽",
                    callback_data=f"journal_{journal['id']}"
                )
            ])
        
        kb.inline_keyboard.append([
            types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
        ])
        
        await message.answer(
            "📚 <b>Доступные выпуски:</b>",
            reply_markup=kb,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Ошибка при получении журналов: {e}")
        await message.answer("❌ Ошибка при загрузке журналов")
        
        
        
@dp.callback_query(F.data.startswith("journal_"))
async def handle_journal_selection(callback: types.CallbackQuery):
    try:
        # Отвечаем сразу чтобы избежать ошибки "query is too old"
        await callback.answer("⏳ Загружаем журнал...")
        
        journal_id = int(callback.data.split("_")[1])
        journal = await db.get_journal_by_id(journal_id)
        
        if not journal:
            await callback.message.answer("❌ Журнал не найден")
            return

        # Получаем актуальное количество
        quantity = journal.get('quantity', 0)
        available_text = f"🛒 В наличии: {quantity} шт." if quantity > 0 else "❌ Нет в наличии"
        
        # Формируем сообщение
        message_text = (
            f"<b>{journal['title']}</b>\n"
            f"Год: {journal['year']}\n"
            f"Цена: {float(journal['price'])}₽\n"
            f"{available_text}\n\n"
        )
        
        # Создаем кнопки
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        
        if quantity > 0:
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text="🛒 Купить сейчас", 
                    web_app=WebAppInfo(
                        url=f"https://tottotdanetot.github.io/iglaboq/frontend/templates/miniapp/shop.html?"
                        f"journal={journal_id}&"
                        f"title={urllib.parse.quote(journal.get('title', ''))}&"
                        f"year={journal.get('year', '')}&"
                        f"price={journal.get('price', '')}&"
                        f"description={urllib.parse.quote(journal.get('description', ''))}&"
                        f"quantity={quantity}&"
                        f"v={int(time.time())}"
                    )
                )
            ])
        
        kb.inline_keyboard.append([
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_journals")
        ])
        
        # Получаем изображения для бота из API
        photo_url = None
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(f'https://dismally-familiar-sharksucker.cloudpub.ru/get_journal_bot_images/{journal_id}') as response:
                    if response.status == 200:
                        response_text = await response.text()
                        
                        try:
                            # Пытаемся распарсить JSON
                            if isinstance(response_text, str):
                                bot_images_data = json.loads(response_text)
                            else:
                                bot_images_data = response_text
                            
                            if isinstance(bot_images_data, dict):
                                bot_images = bot_images_data.get('images', [])
                            else:
                                bot_images = []
                                
                        except json.JSONDecodeError:
                            bot_images = []
                        
                        if bot_images:
                            # Ищем главное изображение или берем первое
                            if isinstance(bot_images[0], dict):
                                main_image = next((img for img in bot_images if img.get('is_main')), bot_images[0])
                                # ИСПОЛЬЗУЕМ РОУТ ДЛЯ ЖУРНАЛОВ С КЭШЕМ!
                                image_filename = main_image['image_url'].split('/')[-1]
                                photo_url = f'https://dismally-familiar-sharksucker.cloudpub.ru/fast_bot_journal/journal_{journal_id}/{image_filename}'
                            else:
                                # ИСПОЛЬЗУЕМ РОУТ ДЛЯ ЖУРНАЛОВ С КЭШЕМ!
                                image_filename = bot_images[0].split('/')[-1]
                                photo_url = f'https://dismally-familiar-sharksucker.cloudpub.ru/fast_bot_journal/journal_{journal_id}/{image_filename}'
            
        except Exception as e:
            logger.error(f"Ошибка при получении изображений бота: {str(e)}")
        
        # Пытаемся отправить с фото - ИСПОЛЬЗУЕМ ПРЯМОЙ URL К НОВОМУ РОУТУ
        if photo_url:
            try:
                logger.info(f"🚀 Trying to send photo with cached URL: {photo_url}")
                
                # ОТПРАВЛЯЕМ ПРЯМО ПО URL К НОВОМУ КЭШИРУЮЩЕМУ РОУТУ
                await callback.message.answer_photo(
                    photo=photo_url,  # ← URL к кэшированному роуту!
                    caption=message_text,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
                logger.info("✅ Photo sent successfully via cached URL")
                return
                
            except Exception as e:
                logger.error(f"❌ Error sending photo via cached URL: {str(e)}")
                
                # Fallback: скачиваем и отправляем как bytes
                try:
                    logger.info("🔄 Trying fallback: download and send as bytes")
                    async with aiohttp.ClientSession() as session:
                        async with session.get(photo_url) as resp:
                            if resp.status == 200:
                                image_data = await resp.read()
                                
                                await callback.message.answer_photo(
                                    photo=types.BufferedInputFile(image_data, filename="journal.jpg"),
                                    caption=message_text,
                                    reply_markup=kb,
                                    parse_mode="HTML"
                                )
                                logger.info("✅ Photo sent via fallback method")
                                return
                            else:
                                logger.error(f"❌ Failed to download image: {resp.status}")
                
                except Exception as fallback_error:
                    logger.error(f"❌ Fallback also failed: {fallback_error}")
        
        # Fallback: отправляем только текст
        logger.info("📝 Sending text only (no photo available)")
        await callback.message.answer(
            message_text,
            reply_markup=kb,
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"❌ Error loading journal: {str(e)}")
        try:
            await callback.message.answer("❌ Произошла ошибка при загрузке журнала")
        except:
            pass
        
        
        
@dp.message(Command("journals"))
async def handle_journals_command(message: types.Message):
    """Обработчик для команды /journals из меню"""
    await show_journals(message)



@dp.message(F.text == "📝 Описание")
async def show_description(message: types.Message):
    """Показ описания"""
    try:
        content_data = await get_bot_content('description')
        
        if not content_data or (not content_data['images'] and not content_data['content']['text_content']):
            await message.answer("Описание пока не добавлено.")
            return
        
        # Отправляем фото если есть
        if content_data['images']:
            main_image = next((img for img in content_data['images'] if img['is_main']), content_data['images'][0])
            
            await message.answer_photo(
                photo=main_image['image_url'],
                caption=content_data['content']['text_content'] or "Описание журнала",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                content_data['content']['text_content'] or "Описание журнала", 
                parse_mode="HTML"
            )
            
    except Exception as e:
        await message.answer("❌ Ошибка загрузки описания")



@dp.message(F.text == "📞 Контакты")
async def show_contacts(message: types.Message):
    """Показ контактов с кнопками"""
    try:
        content_data = await get_bot_content('contacts')
        
        if not content_data or (not content_data['images'] and not content_data['content']['text_content'] and not content_data['buttons']):
            await message.answer("Контакты пока не добавлены.")
            return
        
        # Создаем инлайн клавиатуру
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        
        for btn in content_data['buttons']:
            kb.inline_keyboard.append([
                InlineKeyboardButton(text=btn['button_text'], url=btn['button_url'])
            ])
        
        # Отправляем фото если есть
        if content_data['images']:
            main_image = next((img for img in content_data['images'] if img['is_main']), content_data['images'][0])
            
            await message.answer_photo(
                photo=main_image['image_url'],
                caption=content_data['content']['text_content'] or "Наши контакты",
                reply_markup=kb,
                parse_mode="HTML"
            )
        else:
            await message.answer(
                content_data['content']['text_content'] or "Наши контакты",
                reply_markup=kb,
                parse_mode="HTML"
            )
            
    except Exception as e:
        await message.answer("❌ Ошибка загрузки контактов")



async def get_bot_content(content_type: str):
    """Получить контент из базы"""
    try:
        content = await db.fetch_one(
            "SELECT * FROM bot_content WHERE content_type = %s",
            (content_type,)
        )
        
        if not content:
            return None
        
        images = await db.fetch_all(
            "SELECT * FROM bot_images WHERE content_id = %s ORDER BY is_main DESC, id",
            (content['id'],)
        )
        
        buttons = []
        if content_type == 'contacts':
            buttons = await db.fetch_all(
                "SELECT * FROM bot_buttons WHERE content_id = %s ORDER BY position",
                (content['id'],)
            )
        
        return {
            "content": content,
            "images": images,
            "buttons": buttons
        }
        
    except Exception as e:
        print(f"Error getting bot content: {e}")
        return None
    
    
    
@dp.message(Command("description"))
async def handle_description_command(message: types.Message):
    """Обработчик для команды /description из меню"""
    await show_description(message)



@dp.message(Command("contacts"))
async def handle_contacts_command(message: types.Message):
    """Обработчик для команды /contacts из меню"""
    await show_contacts(message)
    
    

async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="journals", description="Показать журналы"),
        BotCommand(command="description", description="Описание журналов"),
        BotCommand(command="contacts", description="Контакты")
    ]
    await bot.set_my_commands(commands)



async def on_startup(bot: Bot):
    await set_bot_commands(bot)
        



@dp.callback_query(F.data == "back_to_journals")
async def back_to_journals(callback: types.CallbackQuery):
    await show_journals(callback.message)


@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await start(callback.message)



if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

