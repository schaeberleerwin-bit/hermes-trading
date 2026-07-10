"""Plug-and-Play-Backtest von drei SSRN-dokumentierten Cross-Sectional-Faktoren:

  1. Momentum      -- Asness/Frazzini/Israel/Moskowitz, "Fact, Fiction and Momentum
                       Investing" (SSRN #2435323). Publizierter Sharpe: 0.50
  2. Low Volatility -- Blitz/van Vliet, "The Volatility Effect: Lower Risk Without
                       Lower Return" (SSRN #980865). Publizierter Sharpe: 0.72
  3. Betting Against Beta -- Frazzini/Pedersen, "Betting Against Beta". Publizierter
                       Sharpe: 0.42

Keine Optimierung, kein Parameter-Fit -- die Handelsregeln aus den Papers werden
1:1 uebernommen (Long oberstes Terzil, Short unterstes Terzil, Signal exakt ein
Jahr vor heute gebildet, seitdem unveraendert gehalten). Alle drei Faktoren sind
reine Preis-Kennzahlen -- kein Reporting-Lag/Lookahead-Problem wie bei Fundamentaldaten.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quality_screener import DEFAULT_TICKERS

BENCHMARK = "SPY"


def nearest(index: pd.DatetimeIndex, target: pd.Timestamp) -> pd.Timestamp:
    pos = index.searchsorted(target)
    pos = min(max(pos, 0), len(index) - 1)
    return index[pos]


def tercile_long_short(factor: pd.Series, high_is_long: bool):
    factor = factor.dropna()
    ranked = factor.rank(pct=True)
    if high_is_long:
        long_names = ranked[ranked >= 2 / 3].index
        short_names = ranked[ranked <= 1 / 3].index
    else:
        long_names = ranked[ranked <= 1 / 3].index
        short_names = ranked[ranked >= 2 / 3].index
    return list(long_names), list(short_names)


def main() -> None:
    tickers = DEFAULT_TICKERS
    all_symbols = tickers + [BENCHMARK]
    print(f"Lade 5 Jahre Kursdaten fuer {len(all_symbols)} Symbole...")
    raw = yf.download(all_symbols, period="5y", auto_adjust=True, progress=False)["Close"]
    raw = raw.dropna(axis=1, how="all")
    universe = [t for t in tickers if t in raw.columns]

    today = raw.index[-1]
    signal_date = nearest(raw.index, today - pd.Timedelta(days=365))
    mom_start = nearest(raw.index, signal_date - pd.Timedelta(days=365))
    mom_end = nearest(raw.index, signal_date - pd.Timedelta(days=30))
    vol_start = nearest(raw.index, signal_date - pd.Timedelta(days=3 * 365))
    beta_start = nearest(raw.index, signal_date - pd.Timedelta(days=365))

    print(f"Signal-Datum (vor 1 Jahr): {signal_date.date()}  |  Heute: {today.date()}\n")

    daily_ret = raw.pct_change()
    weekly_ret = raw.resample("W").last().pct_change()

    # --- Faktor 1: Momentum (12-1 Monat) ---
    momentum = raw.loc[mom_end, universe] / raw.loc[mom_start, universe] - 1

    # --- Faktor 2: Low Volatility (3J Wochenrendite-Vola) ---
    vol_window = weekly_ret.loc[vol_start:signal_date, universe]
    volatility = vol_window.std()

    # --- Faktor 3: Betting Against Beta (1J Beta ggue. SPY) ---
    beta_window = daily_ret.loc[beta_start:signal_date]
    spy_ret = beta_window[BENCHMARK]
    beta = pd.Series(
        {t: beta_window[t].cov(spy_ret) / spy_ret.var() for t in universe if t in beta_window},
    )

    forward_return = raw.loc[today, universe] / raw.loc[signal_date, universe] - 1
    benchmark_return = raw.loc[today, BENCHMARK] / raw.loc[signal_date, BENCHMARK] - 1
    universe_avg_return = forward_return.mean()

    factors = {
        "Momentum (12-1M)": (momentum, True),          # hohe Vergangenheitsrendite = long
        "Low Volatility (3J)": (volatility, False),     # niedrige Vola = long
        "Betting Against Beta": (beta, False),          # niedriges Beta = long
    }

    print(f"Benchmark SPY Buy&Hold seit Signal-Datum: {benchmark_return * 100:+.1f}%")
    print(f"Aequal-Weight Universe (alle {len(universe)} Ticker):   {universe_avg_return * 100:+.1f}%\n")

    summary = []
    for name, (factor_values, high_is_long) in factors.items():
        long_names, short_names = tercile_long_short(factor_values, high_is_long)
        long_ret = forward_return[long_names].mean()
        short_ret = forward_return[short_names].mean()
        spread = long_ret - short_ret

        print(f"--- {name} ---")
        print(f"  Long  ({len(long_names):2d}): {', '.join(long_names)}")
        print(f"        Forward-Return (1J):  {long_ret * 100:+.1f}%")
        print(f"  Short ({len(short_names):2d}): {', '.join(short_names)}")
        print(f"        Forward-Return (1J):  {short_ret * 100:+.1f}%")
        print(f"  Long-Short-Spread:          {spread * 100:+.1f}%")
        print(f"  Long-Only vs. SPY:          {(long_ret - benchmark_return) * 100:+.1f} pp\n")

        summary.append({
            "factor": name, "long_return_pct": round(long_ret * 100, 1),
            "short_return_pct": round(short_ret * 100, 1), "spread_pct": round(spread * 100, 1),
            "long_vs_spy_pp": round((long_ret - benchmark_return) * 100, 1),
        })

    print("--- Zusammenfassung (ein einziges 1-Jahres-Fenster -- KEIN Sharpe Ratio berechenbar,")
    print("    dafuer braeuchte es viele unabhaengige Perioden. Reine Punkt-zu-Punkt-Rendite.) ---")
    df = pd.DataFrame(summary)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
