import time
from .common import validate

async def fetch(asset: str = "ETH/USDT:USDT") -> dict:
    # Free fallback: neutral macro regime.
    payload = {"schema_version": 1, "asset": asset, "risk_regime": "neutral", "dxy_proxy": 0.0, "ts": time.time()}
    return validate(payload, {"schema_version", "asset", "risk_regime", "dxy_proxy", "ts"}, "macro")
