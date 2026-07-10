"""Plug-and-Play-Backtest: Time-Series-Momentum / Trend-Following.

Regel aus Moskowitz/Ooi/Pedersen, "Time Series Momentum" (SSRN #2089463):
  Am Ende jedes Monats: Signal = Vorzeichen der Rendite der letzten 12 Monate.
  Positiv -> Long fuer den naechsten Monat. Negativ -> Short fuer den naechsten Monat.
Pro Instrument gleichgewichtet, monatlich neu gebildet -- keine Optimierung, kein
Vol-Scaling, kein Parameter-Fit. Getestet ueber diversifizierte Asset-Klassen
(nicht nur Aktien), letzte 12 Monate.
"""

import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

INSTRUMENTS = {
    "SPY": "US-Aktien",
    "QQQ": "US-Tech",
    "TLT": "Langlaufende US-Anleihen",
    "GLD": "Gold",
    "USO": "Rohoel",
    "DBC": "Rohstoffe breit",
    "UUP": "US-Dollar",
    "BTC-USD": "Bitcoin",
}


def main() -> None:
    symbols = list(INSTRUMENTS.keys())
    print(f"Lade 3 Jahre Kursdaten fuer {len(symbols)} Instrumente ueber Asset-Klassen hinweg...")
    raw = yf.download(symbols, period="3y", auto_adjust=True, progress=False)["Close"]
    monthly = raw.resample("ME").last().dropna(how="all")

    today = monthly.index[-1]
    start = monthly.index[monthly.index.get_indexer([today - pd.Timedelta(days=365)], method="nearest")[0]]
    rebalance_dates = monthly.index[(monthly.index >= start) & (monthly.index < today)]

    print(f"Testfenster: {rebalance_dates[0].date()} -> {today.date()} "
          f"({len(rebalance_dates)} monatliche Rebalance-Punkte)\n")

    strat_returns = pd.DataFrame(index=rebalance_dates, columns=symbols, dtype=float)
    bh_returns = pd.DataFrame(index=rebalance_dates, columns=symbols, dtype=float)
    signals = pd.DataFrame(index=rebalance_dates, columns=symbols, dtype=float)

    for dt in rebalance_dates:
        pos = monthly.index.get_loc(dt)
        if pos + 1 >= len(monthly.index):
            continue
        next_dt = monthly.index[pos + 1]
        lookback_pos = monthly.index.get_indexer([dt - pd.Timedelta(days=365)], method="nearest")[0]
        lookback_dt = monthly.index[lookback_pos]

        for sym in symbols:
            p_now, p_next, p_lb = monthly.loc[dt, sym], monthly.loc[next_dt, sym], monthly.loc[lookback_dt, sym]
            if pd.isna(p_now) or pd.isna(p_next) or pd.isna(p_lb):
                continue
            trailing_12m = p_now / p_lb - 1
            signal = 1 if trailing_12m > 0 else -1
            fwd_return = p_next / p_now - 1
            strat_returns.loc[dt, sym] = signal * fwd_return
            bh_returns.loc[dt, sym] = fwd_return
            signals.loc[dt, sym] = signal

    print("--- Pro Instrument (letzte 12 Monate, monatlich rebalanced) ---")
    rows = []
    for sym in symbols:
        s = strat_returns[sym].dropna()
        b = bh_returns[sym].dropna()
        if s.empty:
            continue
        strat_total = (1 + s).prod() - 1
        bh_total = (1 + b).prod() - 1
        long_months = int((signals[sym].dropna() > 0).sum())
        print(f"  {sym:8s} ({INSTRUMENTS[sym]:24s}) Trend-Following: {strat_total*100:+6.1f}%   "
              f"Buy&Hold: {bh_total*100:+6.1f}%   Long-Monate: {long_months}/{len(s)}")
        rows.append({"symbol": sym, "trend_pct": strat_total * 100, "buyhold_pct": bh_total * 100})

    portfolio_strat_monthly = strat_returns.mean(axis=1, skipna=True)
    portfolio_bh_monthly = bh_returns.mean(axis=1, skipna=True)
    portfolio_strat_total = (1 + portfolio_strat_monthly).prod() - 1
    portfolio_bh_total = (1 + portfolio_bh_monthly).prod() - 1

    print("\n--- Portfolio (gleichgewichtet ueber alle 8 Instrumente) ---")
    print(f"  Trend-Following (Long/Short je nach 12M-Signal): {portfolio_strat_total*100:+.1f}%")
    print(f"  Buy&Hold (immer long, gleichgewichtet):          {portfolio_bh_total*100:+.1f}%")
    print(f"\n  (Ein Testjahr = eine Stichprobe. Fuer belastbare Aussagen braeuchte es")
    print(f"   mehrere unabhaengige Marktzyklen, nicht nur 12 Monate.)")


if __name__ == "__main__":
    main()
