#!/bin/bash

# Остановка всех сервисов
echo "🛑 Останавливаем все сервисы..."

# Читаем PIDs из файла
if [ -f pids.txt ]; then
    while read -r pid; do
        kill $pid 2>/dev/null
        echo "❌ Процесс $pid остановлен"
    done < pids.txt
    rm pids.txt
fi

# Дополнительная очистка
pkill -f "python backend/"

echo "✅ Все сервисы остановлены!"