from __future__ import annotations
import asyncio, json, math, random, time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import aiofiles, yaml
from rich.console import Console
from .adapters import price, onchain, news, macro
from .adapters.common import SchemaError

console = Console()
ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"

class CircuitBreaker(RuntimeError): pass

async def retry_adapter(fn, *args, name: str, **kwargs):
    delay = 1
    for attempt in range(3):
        try:
            return await fn(*args, **kwargs)
        except SchemaError:
            raise
        except Exception as e:
            if attempt == 2:
                raise RuntimeError(f"{name} failed after retries: {e}") from e
            await asyncio.sleep(delay)
            delay *= 2

async def append_jsonl(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "a") as f:
        await f.write(json.dumps(obj, sort_keys=True) + "\n")

async def write_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "w") as f:
        await f.write(json.dumps(obj, indent=2, sort_keys=True))

def load_yaml(name: str) -> dict:
    with open(STATE / name, "r") as f:
        return yaml.safe_load(f) or {}

def calc_volatility(history: deque[float]) -> float:
    if len(history) < 3:
        return 0.01
    rets = [math.log(history[i] / history[i-1]) for i in range(1, len(history)) if history[i-1] > 0]
    if len(rets) < 2:
        return 0.01
    avg = sum(rets) / len(rets)
    var = sum((r - avg) ** 2 for r in rets) / (len(rets) - 1)
    return max(math.sqrt(var) * math.sqrt(60), 0.001)

def quote_prices(mid: float, inventory: float, strat: dict, vol: float) -> tuple[float, float]:
    s = strat["strategy"]
    gamma, k, T = float(s["gamma"]), float(s["k"]), float(s["time_horizon"])
    reservation = mid - inventory * gamma * (vol ** 2) * T
    spread_pct = gamma * (vol ** 2) * T + (2 / gamma) * math.log(1 + gamma / k)
    spread_pct = max(spread_pct, float(s["min_spread"]))
    spread_pct = min(spread_pct, float(s["max_spread_percent"]))
    spread = mid * spread_pct
    max_dist = float(s["max_quote_distance_percent"])
    bid = min(reservation - spread / 2, mid * (1 - max_dist))
    ask = max(reservation + spread / 2, mid * (1 + max_dist))
    return round(bid, 4), round(ask, 4)

async def run_loop(asset: str | None = None, once: bool = False):
    goal = load_yaml("goal.yaml")
    strat = load_yaml("strategy.yaml")
    asset = asset or goal.get("asset") or strat.get("trading", {}).get("symbol", "ETH/USDT:USDT")
    exchange_name = strat.get("exchange", {}).get("name", "bybit")
    history = deque(maxlen=int(strat["strategy"].get("sigma_lookback", 100)))
    open_position = None
    equity = float(strat.get("paper", {}).get("starting_equity", 10000.0))
    inventory = 0.0
    failures = 0
    console.print(f"Booting hermes-trading worker | asset={asset} | mode=paper | strategy=v{strat.get('version')}")
    while True:
        try:
            p, oc, nw, ma = await asyncio.gather(
                retry_adapter(price.fetch, asset, exchange_name, name="price"),
                retry_adapter(onchain.fetch, asset, name="onchain"),
                retry_adapter(news.fetch, asset, name="news"),
                retry_adapter(macro.fetch, asset, name="macro"),
            )
            failures = 0
            mid = float(p["mid"])
            history.append(mid)
            vol = calc_volatility(history)
            bid, ask = quote_prices(mid, inventory, strat, vol)
            now = datetime.now(timezone.utc).isoformat()
            trade = None
            # Paper fill model: stochastic fills when quotes are near touch; closes after timeout or stop.
            if open_position is None and random.random() < 0.65:
                side = "buy" if random.random() < 0.5 else "sell"
                entry = bid if side == "buy" else ask
                notional = min(float(strat["risk"]["max_position_size_usd"]), equity * float(strat["trading"].get("order_size_percent", 0.01)))
                qty = notional / entry
                open_position = {"side": side, "entry": entry, "qty": qty, "opened_ts": time.time(), "opened_at": now, "equity_before": equity}
                inventory += qty if side == "buy" else -qty
            elif open_position is not None:
                age_min = (time.time() - open_position["opened_ts"]) / 60
                stop = float(strat["risk"].get("stop_loss_percent", 0.05))
                raw_ret = (mid - open_position["entry"]) / open_position["entry"]
                signed_ret = raw_ret if open_position["side"] == "buy" else -raw_ret
                if age_min >= float(strat.get("paper", {}).get("max_holding_minutes", 15)) or signed_ret <= -stop or random.random() < 0.45:
                    pnl = open_position["equity_before"] * float(strat["trading"].get("order_size_percent", 0.01)) * signed_ret * float(strat["trading"].get("leverage", 1))
                    equity += pnl
                    inventory -= open_position["qty"] if open_position["side"] == "buy" else -open_position["qty"]
                    trade = {"ts": now, "asset": asset, "side": open_position["side"], "entry": open_position["entry"], "exit": mid, "qty": open_position["qty"], "pnl": round(pnl, 6), "return_pct": round(100*pnl/open_position["equity_before"], 6), "equity_before": open_position["equity_before"], "equity_after": equity, "strategy_version": strat.get("version"), "market_regime": ma["risk_regime"], "news_sentiment": nw["sentiment"], "onchain_netflow_z": oc["netflow_z"]}
                    await append_jsonl(STATE / "trades.jsonl", trade)
                    console.print(f"closed paper trade {trade['side']} pnl={trade['pnl']:.4f} equity={equity:.2f}")
                    open_position = None
            await write_json(STATE / "heartbeat.json", {"ts": now, "asset": asset, "mid": mid, "bid": bid, "ask": ask, "volatility": vol, "equity": equity, "inventory": inventory, "open_position": open_position, "last_trade": trade})
            if once:
                return
            await asyncio.sleep(int(strat["strategy"].get("update_frequency", 60)))
        except SchemaError:
            raise
        except Exception as e:
            failures += 1
            console.print(f"worker error {failures}/5: {e}")
            if failures >= 5:
                raise CircuitBreaker("5 consecutive adapter/loop failures") from e
            await asyncio.sleep(5)
