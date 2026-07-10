import os, time, httpx
from .common import validate

async def fetch(asset: str = "ETH/USDT:USDT") -> dict:
    key = os.getenv("NEWS_API_KEY", "")
    sentiment = 0.0
    headlines = []
    if key:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get("https://newsapi.org/v2/everything", params={"q": asset.split('/')[0], "pageSize": 5, "apiKey": key})
                r.raise_for_status()
                headlines = [a.get("title", "") for a in r.json().get("articles", [])]
        except Exception:
            headlines = []
    payload = {"schema_version": 1, "asset": asset, "sentiment": sentiment, "headlines": headlines, "ts": time.time()}
    return validate(payload, {"schema_version", "asset", "sentiment", "headlines", "ts"}, "news")
