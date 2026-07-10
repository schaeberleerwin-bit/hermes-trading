from __future__ import annotations
import argparse, asyncio, yaml
from pathlib import Path
from .loop import run_loop

ROOT = Path(__file__).resolve().parents[1]

def default_asset():
    goal = ROOT / "state" / "goal.yaml"
    if goal.exists():
        return (yaml.safe_load(goal.read_text()) or {}).get("asset")
    return "ETH/USDT:USDT"

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset", default=default_asset(), help="ccxt symbol, default from state/goal.yaml")
    ap.add_argument("--once", action="store_true", help="run one loop iteration for smoke testing")
    args = ap.parse_args()
    asyncio.run(run_loop(asset=args.asset, once=args.once))
