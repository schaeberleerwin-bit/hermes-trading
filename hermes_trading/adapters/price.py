import os, time
import ccxt
from .common import validate

async def fetch(asset: str = "ETH/USDT:USDT", exchange_name: str = "bybit") -> dict:
    exchange_cls = getattr(ccxt, exchange_name)
    cfg = {"enableRateLimit": True, "options": {"defaultType": "future"}}
    if os.getenv("EXCHANGE_API_KEY"):
        cfg["apiKey"] = os.getenv("EXCHANGE_API_KEY")
        cfg["secret"] = os.getenv("EXCHANGE_API_SECRET", "")
    ex = exchange_cls(cfg)
    try:
        orderbook = ex.fetch_order_book(asset, limit=5)
        if not orderbook.get("bids") or not orderbook.get("asks"):
            raise RuntimeError("empty orderbook")
        bid = float(orderbook["bids"][0][0])
        ask = float(orderbook["asks"][0][0])
        payload = {"schema_version": 1, "source": exchange_name, "asset": asset, "bid": bid, "ask": ask, "mid": (bid + ask) / 2, "ts": time.time()}
        return validate(payload, {"schema_version", "asset", "bid", "ask", "mid", "ts"}, "price")
    finally:
        try: ex.close()
        except Exception: pass
