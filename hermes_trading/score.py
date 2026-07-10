from __future__ import annotations
import math
from statistics import mean, pstdev

def _returns(trades):
    vals = []
    for t in trades:
        if "return_pct" in t:
            vals.append(float(t["return_pct"]) / 100.0)
        elif "pnl" in t and "equity_before" in t and t["equity_before"]:
            vals.append(float(t["pnl"]) / float(t["equity_before"]))
    return vals

def _max_drawdown(equity_curve):
    peak = equity_curve[0] if equity_curve else 1.0
    worst = 0.0
    for x in equity_curve:
        peak = max(peak, x)
        worst = min(worst, (x - peak) / peak if peak else 0.0)
    return abs(worst)

def score(trades, goal) -> float:
    """Composite score in [-1,+1] from return, drawdown, and Sharpe."""
    if not trades:
        return 0.0
    rets = _returns(trades)
    if not rets:
        return 0.0
    realised = sum(rets)
    target = float(goal.get("target_return_30d", 0.05))
    ret_component = max(-1.0, min(1.0, realised / target)) if target else 0.0
    equity = [1.0]
    for r in rets:
        equity.append(equity[-1] * (1.0 + r))
    dd = _max_drawdown(equity)
    max_dd = float(goal.get("max_drawdown", 0.08))
    dd_component = 1.0 - min(2.0, dd / max_dd) if max_dd else 0.0
    sd = pstdev(rets) if len(rets) > 1 else 0.0
    sharpe = (mean(rets) / sd * math.sqrt(len(rets))) if sd else (1.0 if mean(rets) > 0 else 0.0)
    min_sharpe = float(goal.get("min_sharpe", 1.2))
    sharpe_component = max(-1.0, min(1.0, sharpe / min_sharpe)) if min_sharpe else 0.0
    composite = 0.45 * ret_component + 0.35 * dd_component + 0.20 * sharpe_component
    floor = float(goal.get("failure_below", -0.04))
    if realised < floor:
        composite -= 0.25
    return round(max(-1.0, min(1.0, composite)), 4)
