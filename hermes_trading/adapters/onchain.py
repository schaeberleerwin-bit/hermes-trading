import time
from .common import validate

async def fetch(asset: str = "ETH/USDT:USDT") -> dict:
    # Free fallback: neutral on-chain signal. Premium Glassnode can be wired via GLASSNODE_API_KEY.
    payload = {"schema_version": 1, "asset": asset, "active_addresses_z": 0.0, "netflow_z": 0.0, "ts": time.time()}
    return validate(payload, {"schema_version", "asset", "active_addresses_z", "netflow_z", "ts"}, "onchain")
