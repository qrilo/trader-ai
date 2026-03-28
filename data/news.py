from dataclasses import dataclass
from datetime import datetime, timedelta

import feedparser
import requests
from loguru import logger


CRYPTO_PANIC_RSS = "https://cryptopanic.com/news/rss/"
COINDESK_RSS = "https://www.coindesk.com/arc/outboundfeeds/rss/"
COINTELEGRAPH_RSS = "https://cointelegraph.com/rss"

SYMBOL_KEYWORDS = {
    "BTC/USDT": ["bitcoin", "btc"],
    "ETH/USDT": ["ethereum", "eth"],
    "SOL/USDT": ["solana", "sol"],
}


@dataclass
class NewsItem:
    title: str
    summary: str
    published: datetime
    source: str


def fetch_news(symbol: str, hours: int = 4) -> list[NewsItem]:
    """Получить последние новости по символу за последние N часов."""
    keywords = SYMBOL_KEYWORDS.get(symbol, [])
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    news_items = []

    for feed_url in [COINDESK_RSS, COINTELEGRAPH_RSS]:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                title = entry.get("title", "").lower()
                summary = entry.get("summary", "").lower()

                # Фильтр по ключевым словам символа или общие крипто-новости
                is_relevant = any(kw in title or kw in summary for kw in keywords) or any(
                    kw in title for kw in ["crypto", "market", "defi", "blockchain"]
                )

                if not is_relevant:
                    continue

                published_str = entry.get("published", "")
                try:
                    published = datetime(*entry.published_parsed[:6])
                except Exception:
                    published = datetime.utcnow()

                if published < cutoff:
                    continue

                news_items.append(
                    NewsItem(
                        title=entry.get("title", ""),
                        summary=entry.get("summary", "")[:500],
                        published=published,
                        source=feed_url,
                    )
                )
        except Exception as e:
            logger.warning(f"Ошибка загрузки новостей с {feed_url}: {e}")

    logger.debug(f"Найдено {len(news_items)} новостей по {symbol}")
    return news_items[:20]
