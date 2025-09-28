FROM python:3.9

WORKDIR /app

# Копируем requirements.txt первым для кэширования
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальные файлы
COPY . .

# Добавляем backend в PYTHONPATH
ENV PYTHONPATH="${PYTHONPATH}:/app/backend"

# Указываем рабочую директорию
WORKDIR /app/backend

CMD ["python", "bot_main.py"]