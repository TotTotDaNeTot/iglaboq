#!/bin/bash

# Запуск всех сервисов в фоне
echo "🚀 Запуск всех сервисов..."

# Бот
python backend/bot_main.py &
BOT_PID=$!
echo "🤖 Бот запущен (PID: $BOT_PID)"

# FastAPI сервер 
cd backend && uvicorn fast_app:app --host 0.0.0.0 --port 5006 &
FASTAPI_PID=$!
echo "🌐 FastAPI сервер запущен (PID: $FASTAPI_PID)"

# Flask сервер
python backend/start_app.py &
FLASK_PID=$!
echo "🖥️ Flask сервер запущен (PID: $FLASK_PID)"

# Обработчик платежей
python backend/payment_handler.py &
PAYMENT_PID=$!
echo "💳 Обработчик платежей запущен (PID: $PAYMENT_PID)"

# Сохраняем PIDs в файл
echo $BOT_PID $FASTAPI_PID $FLASK_PID $PAYMENT_PID > pids.txt

echo "✅ Все сервисы запущены!"
echo "📋 PIDs сохранены в pids.txt"
echo "🛑 Для остановки: ./stop.sh"