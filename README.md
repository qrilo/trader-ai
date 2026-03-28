# TRAIDER

AI-трейдер с человеческим апрувом. Система анализирует крипторынок 24/7,
находит торговые возможности и отправляет сигнал в Telegram. Ты нажимаешь
"Войти" — сделка исполняется автоматически на Binance.

**Принцип:** AI делает всю работу, человек принимает финальное решение.

---

## Как это работает

```
Каждые 15 минут:

Binance (реальные данные) → Индикаторы → XGBoost модель → Сигнал
                                                               ↓
                                              Telegram: карточка сделки
                                                               ↓
                                              Ты: ✅ Войти / ❌ Пропустить
                                                               ↓
                                              Binance: ордер + SL + TP
                                                               ↓
                                              Telegram: результат сделки
```

---

## Быстрый старт

### 1. Получить ключи

- **Binance API** — [binance.com/en/my/settings/api-management](https://www.binance.com/en/my/settings/api-management)
  Разрешения: ✅ Enable Reading + ✅ Enable Futures
- **Telegram Bot Token** — написать @BotFather → `/newbot`
- **Telegram Chat ID** — написать @userinfobot

### 2. Настроить окружение

```bash
cp .env.example .env
# Заполнить .env своими ключами
```

### 3. Запустить

```bash
docker compose up --build
```

Всё происходит автоматически:
1. Поднимается PostgreSQL
2. Запускается trainer:
   - Если модель не обучена → скачивает 2 года данных с Binance и обучает (~10 мин)
   - Если модель актуальна (< 30 дней) → пропускает, стартует мгновенно
   - Если модель старше 30 дней → переобучает на свежих данных
3. Запускается бот — анализирует рынок каждые 15 минут

### 4. Принудительно переобучить модель

```bash
docker compose down && docker compose up --build
# trainer автоматически переобучит если модель старше 30 дней
```

---

## Команды Telegram-бота

| Команда | Описание |
|---|---|
| `/start` | Приветствие и список команд |
| `/balance` | Баланс фьючерсного кошелька |
| `/stats` | Статистика всех сделок (winrate, PnL) |
| `/positions` | Текущие открытые позиции |
| `/report` | Отчёт за последние 7 дней |

---

## Параметры (.env)

| Параметр | По умолчанию | Описание |
|---|---|---|
| `BINANCE_API_KEY` | — | API ключ Binance |
| `BINANCE_API_SECRET` | — | API секрет Binance |
| `BINANCE_TESTNET` | false | true = Testnet, false = реальный счёт |
| `TELEGRAM_BOT_TOKEN` | — | Токен Telegram-бота |
| `TELEGRAM_CHAT_ID` | — | Твой Telegram ID |
| `RISK_PER_TRADE` | 0.02 | Риск на сделку (2% депозита) |
| `MAX_OPEN_POSITIONS` | 2 | Максимум открытых позиций |
| `MIN_CONFIDENCE` | 0.65 | Минимальная уверенность ML (65%) |
| `SIGNAL_TIMEOUT_MINUTES` | 10 | Таймаут апрува сигнала |
| `MIN_RR_RATIO` | 2.0 | Минимальный R/R (1:2) |
| `TRADING_SYMBOLS` | BTC/USDT | Торгуемые пары (через запятую) |
| `TIMEFRAME` | 15m | Таймфрейм анализа |

---

## Структура проекта

```
traider/
├── data/
│   ├── collector.py      # Свечи с Binance (реальный рынок)
│   ├── indicators.py     # RSI, MACD, Bollinger, EMA, ATR, объём
│   └── news.py           # Новости (CryptoPanic, CoinDesk RSS)
├── models/
│   ├── trainer.py        # Обучение XGBoost (умный: пропускает актуальные)
│   ├── predictor.py      # Предсказание вероятности роста
│   ├── sentiment.py      # FinBERT — анализ новостей локально
│   └── saved/            # Обученные модели (не в git)
├── signals/
│   ├── generator.py      # Генерация сигналов
│   ├── risk.py           # Расчёт SL/TP/размера позиции по ATR
│   └── formatter.py      # Форматирование карточек для Telegram
├── trading/
│   ├── exchange.py       # Binance API (ордера)
│   ├── order_manager.py  # Открытие позиций
│   └── position_tracker.py # Мониторинг → закрытие → уведомление
├── bot/
│   ├── telegram_bot.py   # Команды бота
│   ├── handlers.py       # Кнопки апрува/отклонения
│   └── notifications.py  # Отправка сообщений
├── database/
│   ├── models.py         # Таблицы: сигналы, сделки, статистика
│   └── repository.py     # CRUD операции
├── scheduler/
│   └── jobs.py           # Анализ каждые 15 мин, отчёт по воскресеньям
├── docker-compose.yml    # PostgreSQL + trainer + бот
├── Dockerfile
├── config.py             # Все настройки из .env
├── main.py               # Точка входа
└── requirements.txt
```

---

## Риск-менеджмент (встроен)

- **2% депозита** на одну сделку (настраивается)
- **Максимум 2** открытые позиции одновременно
- **Stop Loss** на каждой сделке (рассчитывается по ATR)
- **Минимальный R/R = 1:2** — прибыль минимум в 2 раза больше риска
- **Таймаут 10 минут** — не апрувнул → сигнал сгорает

---

## Уведомления в Telegram

**Новый сигнал:**
```
🔔 Сигнал: BTC/USDT LONG
📈 Вход:        $84,200
🛑 Stop Loss:   $82,500  (-2%)
🎯 Take Profit: $88,000  (+4.5%)
💰 Размер:      $500
📊 R/R:         1 : 2.25
🤖 Уверенность: 71%
[✅ Войти]  [❌ Пропустить]
```

**Результат сделки:**
```
✅ Сделка закрыта — ПРИБЫЛЬ
BTC/USDT LONG: +$180 (+3.8%)
Winrate: 24 сделки | 67% побед | PnL: +$1,240
```

**Еженедельный отчёт** — каждое воскресенье автоматически.

---

## Технологии

| Компонент | Технология |
|---|---|
| Язык | Python 3.11 |
| Биржа | Binance Futures (ccxt) |
| ML-модель | XGBoost + scikit-learn |
| Индикаторы | ta (technical analysis) |
| Сентимент новостей | FinBERT (локально, без API) |
| База данных | PostgreSQL + SQLAlchemy |
| Telegram | python-telegram-bot |
| Инфраструктура | Docker Compose |

**Стоимость: $0/месяц** — всё локально, без внешних платных API.
