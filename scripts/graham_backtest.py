"""Backtest der Graham-Zahl-Regel (Ratio > 1 = kaufen, < 1 = verkaufen/meiden).

Kein Parameter-Fit, keine Optimierung -- die Regel wird 1:1 mit dem Schwellwert 1.0
gegen historische Daten getestet. Signal wird aus dem Jahresbericht gebildet, der
~1 Jahr vor heute bereits oeffentlich war (Reporting-Lag beruecksichtigt, damit
kein Lookahead-Bias entsteht). Verglichen wird die Buy&Hold-Rendite seitdem.

Nutzung:
    python graham_backtest.py                    # Default-Universe
    python graham_backtest.py AAPL MSFT KO ...    # eigene Ticker
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quality_screener import DEFAULT_TICKERS

BACKTEST_DAYS = 365
REPORTING_LAG_DAYS = 75  # Zeit zw. Bilanzstichtag und Veroeffentlichung (10-K/GB)


def graham_number(eps: float, bvps: float):
    if eps is None or bvps is None or eps <= 0 or bvps <= 0:
        return None
    return float(np.sqrt(22.5 * eps * bvps))


def nearest_price(hist: pd.Series, target: pd.Timestamp):
    idx = hist.index
    if idx.tz is not None and target.tz is None:
        target = target.tz_localize(idx.tz)
    pos = idx.searchsorted(target)
    pos = min(max(pos, 0), len(idx) - 1)
    return float(hist.iloc[pos]), idx[pos]


def backtest_one(ticker: str, today: pd.Timestamp, backtest_start: pd.Timestamp):
    t = yf.Ticker(ticker)
    income = t.income_stmt
    balance = t.balance_sheet
    hist = t.history(period="2y")["Close"]
    if income.empty or balance.empty or hist.empty:
        return None

    candidates = [c for c in income.columns if c + pd.Timedelta(days=REPORTING_LAG_DAYS) <= backtest_start]
    if not candidates:
        return None
    fy_date = max(candidates)
    bal_candidates = [c for c in balance.columns if c <= fy_date + pd.Timedelta(days=10)]
    if not bal_candidates:
        return None
    bal_date = max(bal_candidates)

    eps_then = income.loc["Diluted EPS", fy_date] if "Diluted EPS" in income.index else None
    equity = balance.loc["Stockholders Equity", bal_date] if "Stockholders Equity" in balance.index else None
    shares = balance.loc["Ordinary Shares Number", bal_date] if "Ordinary Shares Number" in balance.index else None
    bvps_then = (equity / shares) if (equity is not None and shares) else None

    gn_then = graham_number(eps_then, bvps_then)
    price_then, price_then_date = nearest_price(hist, backtest_start)
    price_now, price_now_date = nearest_price(hist, today)

    info = t.info
    gn_now = graham_number(info.get("trailingEps"), info.get("bookValue"))

    if gn_then is None:
        return {
            "ticker": ticker, "skip_reason": "negative/fehlende EPS oder Buchwert im Referenzjahr",
        }

    ratio_then = gn_then / price_then
    signal_then = "kaufen" if ratio_then > 1 else "meiden"
    buy_hold_return = price_now / price_then - 1
    strategy_return = buy_hold_return if signal_then == "kaufen" else 0.0

    ratio_now = (gn_now / price_now) if gn_now else None
    signal_now = ("kaufen" if ratio_now > 1 else "meiden") if ratio_now else "n/a"

    return {
        "ticker": ticker,
        "fy_used": fy_date.strftime("%Y-%m-%d"),
        "signal_date": price_then_date.strftime("%Y-%m-%d"),
        "graham_then": round(gn_then, 2),
        "price_then": round(price_then, 2),
        "ratio_then": round(ratio_then, 2),
        "signal_then": signal_then,
        "price_now": round(price_now, 2),
        "buy_hold_return_pct": round(buy_hold_return * 100, 1),
        "strategy_return_pct": round(strategy_return * 100, 1),
        "ratio_now": round(ratio_now, 2) if ratio_now else None,
        "signal_now": signal_now,
    }


def main() -> None:
    tickers = sys.argv[1:] or DEFAULT_TICKERS
    today = pd.Timestamp.now(tz=None).normalize()
    backtest_start = today - pd.Timedelta(days=BACKTEST_DAYS)

    print(f"Backtest-Fenster: {backtest_start.date()} -> {today.date()} "
          f"(Signal-Fundamentaldaten mit {REPORTING_LAG_DAYS} Tagen Lag, kein Lookahead)\n")

    results, skipped = [], []
    for tk in tickers:
        try:
            r = backtest_one(tk, today, backtest_start)
        except Exception as e:
            r = {"ticker": tk, "skip_reason": str(e)}
        if r is None:
            skipped.append({"ticker": tk, "skip_reason": "keine ausreichenden historischen Daten"})
        elif "skip_reason" in r:
            skipped.append(r)
        else:
            results.append(r)
            print(f"  ok {tk}: Signal am {r['signal_date']} = {r['signal_then']:6s} "
                  f"(Ratio {r['ratio_then']})  ->  Buy&Hold {r['buy_hold_return_pct']:+.1f}%  "
                  f"Strategie {r['strategy_return_pct']:+.1f}%")

    for s in skipped:
        print(f"  -- {s['ticker']}: uebersprungen ({s['skip_reason']})")

    if not results:
        print("\nKeine auswertbaren Ticker.")
        return

    df = pd.DataFrame(results)
    n_buy = (df["signal_then"] == "kaufen").sum()
    n_avoid = (df["signal_then"] == "meiden").sum()
    avg_bh_all = df["buy_hold_return_pct"].mean()
    avg_strat_all = df["strategy_return_pct"].mean()
    avg_bh_buy = df.loc[df["signal_then"] == "kaufen", "buy_hold_return_pct"].mean() if n_buy else float("nan")
    avg_bh_avoid = df.loc[df["signal_then"] == "meiden", "buy_hold_return_pct"].mean() if n_avoid else float("nan")

    print("\n--- Zusammenfassung ---")
    print(f"Ausgewertet: {len(df)}  |  Signal 'kaufen': {n_buy}  |  Signal 'meiden': {n_avoid}")
    print(f"Avg. Buy&Hold  (alle Ticker):            {avg_bh_all:+.1f}%")
    print(f"Avg. Strategie (Graham-Regel angewandt): {avg_strat_all:+.1f}%")
    if n_buy:
        print(f"Avg. Buy&Hold nur der 'kaufen'-Signale:   {avg_bh_buy:+.1f}%")
    if n_avoid:
        print(f"Avg. Buy&Hold nur der 'meiden'-Signale:   {avg_bh_avoid:+.1f}%  (waere entgangen)")

    out_dir = Path(__file__).resolve().parent.parent / "state"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "graham_backtest.json"
    out_path.write_text(json.dumps({"results": results, "skipped": skipped}, indent=2), encoding="utf-8")
    print(f"\nDetails: {out_path}")


if __name__ == "__main__":
    main()
