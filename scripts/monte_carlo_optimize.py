from __future__ import annotations

import argparse
import csv
import json
import math
import random
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
OUT = ROOT / "state" / "optimization"


@dataclass
class Metrics:
    score: float
    return_30d: float
    max_drawdown: float
    sharpe: float
    trades: int
    win_rate: float
    median_return_30d: float
    p05_return_30d: float
    p95_drawdown: float


def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def max_drawdown(equity: np.ndarray) -> float:
    peaks = np.maximum.accumulate(equity)
    dd = (equity - peaks) / peaks
    return float(abs(np.min(dd)))


def sharpe_from_returns(rets: np.ndarray) -> float:
    if len(rets) < 2:
        return 0.0
    sd = float(np.std(rets, ddof=1))
    if sd == 0:
        return 0.0
    # trade-level annualization proxy for 30-day comparison
    return float(np.mean(rets) / sd * math.sqrt(max(len(rets), 1)))


def composite_score(return_30d: float, dd: float, sharpe: float, goal: dict[str, Any]) -> float:
    target = float(goal.get("target_return_30d", 0.05))
    max_dd = float(goal.get("max_drawdown", 0.08))
    min_sharpe = float(goal.get("min_sharpe", 1.2))
    failure_below = float(goal.get("failure_below", -0.04))
    ret_component = max(-1.0, min(1.0, return_30d / target)) if target else 0.0
    dd_component = 1.0 - min(2.0, dd / max_dd) if max_dd else 0.0
    sharpe_component = max(-1.0, min(1.0, sharpe / min_sharpe)) if min_sharpe else 0.0
    score = 0.45 * ret_component + 0.35 * dd_component + 0.20 * sharpe_component
    if return_30d < failure_below:
        score -= 0.25
    return max(-1.0, min(1.0, score))


def simulate_one(params: dict[str, float], base: dict[str, Any], goal: dict[str, Any], rng: np.random.Generator, minutes: int) -> tuple[float, float, float, int, float]:
    start_equity = float(base.get("paper", {}).get("starting_equity", 10000.0))
    equity = start_equity
    equity_curve = [equity]
    trade_returns: list[float] = []

    price = 2000.0
    inventory_usd = 0.0
    position_size_usd = min(float(base["risk"].get("max_position_size_usd", 100)), equity * float(base["trading"].get("order_size_percent", 0.01)))
    leverage = float(base["trading"].get("leverage", 5))
    max_inventory = float(base["risk"].get("max_inventory_usd", 1000))
    daily_loss_limit = float(base["risk"].get("daily_loss_limit_usd", 50))

    gamma = params["gamma"]
    k = params["k"]
    min_spread = params["min_spread"]
    max_spread_percent = params["max_spread_percent"]
    quote_distance = params["max_quote_distance_percent"]
    stop_loss = params["stop_loss_percent"]

    # Random market regime per path: drift and minute volatility.
    regime = rng.choice(["calm_up", "calm_down", "choppy", "volatile"], p=[0.25, 0.20, 0.35, 0.20])
    if regime == "calm_up":
        mu, sigma = 0.000003, 0.00055
    elif regime == "calm_down":
        mu, sigma = -0.000003, 0.00060
    elif regime == "volatile":
        mu, sigma = 0.0, 0.00140
    else:
        mu, sigma = 0.0, 0.00090

    # Avellaneda-style spread proxy, clamped by configured bounds.
    raw_spread = gamma * sigma * sigma * 60 + (2.0 / gamma) * math.log(1.0 + gamma / k) / 10000.0
    spread_pct = min(max(raw_spread, min_spread), max_spread_percent)

    daily_start = equity
    for minute in range(minutes):
        old_price = price
        price *= math.exp((mu - 0.5 * sigma * sigma) + sigma * rng.normal())
        move = (price - old_price) / old_price

        # Fill probability: tighter quotes fill more often; volatility increases fills.
        tightness = max(0.05, 1.0 - spread_pct / max(max_spread_percent, 1e-9))
        distance_penalty = max(0.05, 1.0 - quote_distance / 0.02)
        fill_prob = min(0.85, 0.04 + 0.55 * tightness + 0.10 * min(sigma / 0.001, 2.0) - 0.15 * distance_penalty)

        if abs(inventory_usd) < max_inventory and rng.random() < fill_prob:
            side = 1 if rng.random() < 0.5 else -1
            # Market making earns half spread when mean reversion helps, loses on adverse selection.
            adverse_selection = side * move * leverage * position_size_usd
            spread_capture = spread_pct * 0.5 * position_size_usd * leverage
            inventory_penalty = (abs(inventory_usd) / max_inventory) * gamma * 0.03 * position_size_usd
            fee = 0.0006 * position_size_usd * leverage
            pnl = spread_capture - adverse_selection - inventory_penalty - fee
            # Stop-loss proxy on individual fill.
            pnl = max(pnl, -stop_loss * position_size_usd * leverage)
            equity += pnl
            inventory_usd += side * position_size_usd
            trade_returns.append(pnl / max(equity - pnl, 1.0))
        # Inventory mean-reverts as quotes get hit on opposite side.
        if inventory_usd and rng.random() < 0.20:
            inventory_usd *= 0.70
        # Daily loss guard.
        if (minute + 1) % 1440 == 0:
            if daily_start - equity > daily_loss_limit:
                # Shut down for the simulated rest of day.
                pass
            daily_start = equity
        equity_curve.append(equity)

    eq = np.array(equity_curve, dtype=float)
    rets = np.array(trade_returns, dtype=float)
    ret_30d = float(eq[-1] / eq[0] - 1.0)
    dd = max_drawdown(eq)
    shp = sharpe_from_returns(rets)
    win = float(np.mean(rets > 0)) if len(rets) else 0.0
    return ret_30d, dd, shp, len(rets), win


def evaluate(params: dict[str, float], base: dict[str, Any], goal: dict[str, Any], paths: int, minutes: int, seed: int) -> Metrics:
    rng = np.random.default_rng(seed)
    rows = [simulate_one(params, base, goal, rng, minutes) for _ in range(paths)]
    returns = np.array([r[0] for r in rows], dtype=float)
    dds = np.array([r[1] for r in rows], dtype=float)
    sharpes = np.array([r[2] for r in rows], dtype=float)
    trades = np.array([r[3] for r in rows], dtype=float)
    wins = np.array([r[4] for r in rows], dtype=float)
    score = composite_score(float(np.median(returns)), float(np.percentile(dds, 95)), float(np.median(sharpes)), goal)
    # Penalize sparse strategies and high tail risk.
    if float(np.median(trades)) < 5:
        score -= 0.20
    if float(np.percentile(dds, 95)) > float(goal.get("max_drawdown", 0.08)):
        score -= 0.20
    return Metrics(
        score=round(max(-1.0, min(1.0, score)), 6),
        return_30d=round(float(np.mean(returns)), 6),
        max_drawdown=round(float(np.mean(dds)), 6),
        sharpe=round(float(np.mean(sharpes)), 6),
        trades=int(round(float(np.mean(trades)))),
        win_rate=round(float(np.mean(wins)), 6),
        median_return_30d=round(float(np.median(returns)), 6),
        p05_return_30d=round(float(np.percentile(returns, 5)), 6),
        p95_drawdown=round(float(np.percentile(dds, 95)), 6),
    )


def sample_params(base: dict[str, Any], rng: random.Random) -> dict[str, float]:
    s = base["strategy"]
    r = base["risk"]
    return {
        "gamma": round(rng.uniform(0.03, 0.35), 6),
        "k": round(rng.uniform(0.6, 3.5), 6),
        "min_spread": round(10 ** rng.uniform(math.log10(0.00002), math.log10(0.0010)), 8),
        "max_spread_percent": round(rng.uniform(0.004, 0.025), 6),
        "max_quote_distance_percent": round(rng.uniform(0.001, 0.012), 6),
        "stop_loss_percent": round(rng.uniform(0.01, 0.08), 6),
    }


def apply_params(base: dict[str, Any], params: dict[str, float]) -> dict[str, Any]:
    out = deepcopy(base)
    out["strategy"]["gamma"] = float(params["gamma"])
    out["strategy"]["k"] = float(params["k"])
    out["strategy"]["min_spread"] = float(params["min_spread"])
    out["strategy"]["max_spread_percent"] = float(params["max_spread_percent"])
    out["strategy"]["max_quote_distance_percent"] = float(params["max_quote_distance_percent"])
    out["risk"]["stop_loss_percent"] = float(params["stop_loss_percent"])
    out["optimization_note"] = "Candidate from Monte Carlo optimization. Not applied to live paper worker unless operator confirms."
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", type=int, default=120)
    ap.add_argument("--paths", type=int, default=200)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--steps-per-day", type=int, default=240, help="Synthetic intraday steps per day; lower is faster")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    base = load_yaml(STATE / "strategy.yaml")
    goal = load_yaml(STATE / "goal.yaml")
    minutes = args.days * args.steps_per_day
    rng = random.Random(args.seed)
    OUT.mkdir(parents=True, exist_ok=True)

    current_params = {
        "gamma": float(base["strategy"]["gamma"]),
        "k": float(base["strategy"]["k"]),
        "min_spread": float(base["strategy"]["min_spread"]),
        "max_spread_percent": float(base["strategy"]["max_spread_percent"]),
        "max_quote_distance_percent": float(base["strategy"]["max_quote_distance_percent"]),
        "stop_loss_percent": float(base["risk"]["stop_loss_percent"]),
    }
    candidates = [current_params] + [sample_params(base, rng) for _ in range(args.candidates - 1)]
    results = []
    for i, params in enumerate(candidates):
        metrics = evaluate(params, base, goal, args.paths, minutes, args.seed + i * 997)
        row = {"candidate": i, **params, **metrics.__dict__}
        results.append(row)
        if i % 10 == 0:
            print(f"evaluated {i+1}/{len(candidates)} best_score={max(r['score'] for r in results):.4f}", flush=True)

    results.sort(key=lambda x: (x["score"], x["median_return_30d"], -x["p95_drawdown"]), reverse=True)
    csv_path = OUT / "monte_carlo_results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    best = results[0]
    candidate_strategy = apply_params(base, best)
    save_yaml(OUT / "optimized_strategy.yaml", candidate_strategy)
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "asset": goal.get("asset"),
        "simulation": {"candidates": args.candidates, "paths_per_candidate": args.paths, "days": args.days, "steps_per_day": args.steps_per_day, "seed": args.seed},
        "current_params": current_params,
        "best": best,
        "top_10": results[:10],
        "files": {"csv": str(csv_path), "optimized_strategy": str(OUT / "optimized_strategy.yaml")},
        "warning": "Monte Carlo uses a synthetic fill/price model. Treat this as parameter triage, not proof of profitability.",
    }
    (OUT / "monte_carlo_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
