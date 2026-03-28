from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from loguru import logger

from data.news import NewsItem, fetch_news


@dataclass
class SentimentResult:
    score: float        # от -1.0 (негатив) до +1.0 (позитив)
    label: str          # "Позитивный" / "Нейтральный" / "Негативный"
    news_count: int     # сколько новостей проанализировано


@lru_cache(maxsize=1)
def _load_finbert():
    """Загружает FinBERT один раз и кеширует в памяти."""
    from transformers import pipeline
    logger.info("Загрузка FinBERT модели (первый запуск займёт несколько минут)...")
    classifier = pipeline(
        "text-classification",
        model="ProsusAI/finbert",
        tokenizer="ProsusAI/finbert",
        device=-1,  # CPU
    )
    logger.info("FinBERT загружен")
    return classifier


def _label_to_score(label: str) -> float:
    """Конвертировать метку FinBERT в числовой скор."""
    mapping = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
    return mapping.get(label.lower(), 0.0)


def _score_to_label(score: float) -> str:
    if score > 0.2:
        return "Позитивный"
    elif score < -0.2:
        return "Негативный"
    return "Нейтральный"


def analyze_sentiment(symbol: str) -> SentimentResult:
    """
    Получить новости по символу и проанализировать сентимент через FinBERT.
    При ошибке возвращает нейтральный результат.
    """
    news_items: list[NewsItem] = fetch_news(symbol)

    if not news_items:
        logger.debug(f"Нет новостей для {symbol}, сентимент = нейтральный")
        return SentimentResult(score=0.0, label="Нейтральный", news_count=0)

    try:
        classifier = _load_finbert()
        texts = [item.title + ". " + item.summary[:200] for item in news_items]

        scores = []
        for text in texts:
            result = classifier(text[:512], truncation=True)[0]
            scores.append(_label_to_score(result["label"]) * result["score"])

        avg_score = sum(scores) / len(scores)
        label = _score_to_label(avg_score)

        logger.debug(f"Сентимент {symbol}: {avg_score:.3f} ({label}), новостей: {len(news_items)}")
        return SentimentResult(score=avg_score, label=label, news_count=len(news_items))

    except Exception as e:
        logger.error(f"Ошибка анализа сентимента {symbol}: {e}")
        return SentimentResult(score=0.0, label="Нейтральный", news_count=0)
