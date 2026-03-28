# TRAIDER

AI-трейдер с человеческим апрувом. Система анализирует крипторынок 24/7,
находит торговые возможности и отправляет сигнал в Telegram. Ты нажимаешь
"Войти" — сделка исполняется автоматически на Binance.

## Быстрый старт (через Docker — рекомендуется)

### 1. Настроить окружение

```bash
cp .env.example .env
# Открыть .env и заполнить все значения
```

Что нужно:
- **Binance Testnet API**: зарегистрироваться на [testnet.binancefutures.com](https://testnet.binancefutures.com)
- **Telegram Bot Token**: написать @BotFather → /newbot
- **Telegram Chat ID**: написать @userinfobot

### 2. Обучить ML-модели (один раз)

```bash
docker compose --profile train up trainer --build
```

Что происходит:
- Скачивает 2 года свечей BTC/ETH/SOL с Binance
- Рассчитывает индикаторы
- Обучает XGBoost для каждого символа
- Сохраняет модели в `models/saved/`

Занимает **5-15 минут**. После завершения контейнер сам останавливается.
Модели сохраняются локально — при перезапуске бота переобучать не нужно.

Переобучать раз в месяц на свежих данных:
```bash
docker compose --profile train up trainer
```

### 3. Запустить бота

```bash
docker compose up --build
```

Поднимается PostgreSQL + TRAIDER. Логи видны в терминале.
Для запуска в фоне: `docker compose up -d --build`

### 4. Посмотреть логи

```bash
docker compose logs -f traider
```

### 5. Остановить

```bash
docker compose down
```

## Команды Telegram-бота

| Команда | Описание |
|---|---|
| `/start` | Приветствие и список команд |
| `/stats` | Статистика всех сделок |
| `/positions` | Текущие открытые позиции |
| `/report` | Отчёт за последние 7 дней |

## Структура проекта

```
traider/
├── data/           # Сбор данных с Binance + технические индикаторы + новости
├── models/         # XGBoost (обучение + предсказание) + FinBERT (сентимент)
├── signals/        # Генератор сигналов + риск-менеджмент + форматирование
├── trading/        # Исполнение ордеров + мониторинг позиций
├── bot/            # Telegram-бот + обработчики кнопок + уведомления
├── database/       # Модели SQLAlchemy + CRUD операции
├── scheduler/      # Расписание задач
├── config.py       # Конфигурация
└── main.py         # Точка входа
```

## Параметры (.env)

| Параметр | По умолчанию | Описание |
|---|---|---|
| `RISK_PER_TRADE` | 0.05 | Риск на сделку (5% депозита) |
| `MAX_OPEN_POSITIONS` | 3 | Максимум открытых позиций |
| `MIN_CONFIDENCE` | 0.65 | Минимальная уверенность ML (65%) |
| `SIGNAL_TIMEOUT_MINUTES` | 10 | Таймаут апрува сигнала |
| `MIN_RR_RATIO` | 2.0 | Минимальный R/R (1:2) |
| `TRADING_SYMBOLS` | BTC/USDT,ETH/USDT,SOL/USDT | Торгуемые пары |
| `TIMEFRAME` | 15m | Таймфрейм свечей |
| `BINANCE_TESTNET` | true | Testnet или реальный аккаунт |
