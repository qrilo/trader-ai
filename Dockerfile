FROM python:3.11-slim

WORKDIR /app

# Системные зависимости для psycopg2 и torch
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Сначала копируем только requirements для кеширования слоёв
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Создаём нужные директории
RUN mkdir -p logs models/saved

CMD ["python", "main.py"]
