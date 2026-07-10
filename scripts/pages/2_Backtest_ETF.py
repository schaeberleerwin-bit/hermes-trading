"""Seite: Backtest der Sektor-ETF-Rotation (validierte Original-Strategie)."""

import plotly.graph_objects as go
import streamlit as st

from sector_rotation_lib import (
    SECTOR_ETFS, backtest_etf_rotation, basket_log_to_df, equity_in_capital, render_monthly_returns_pager,
    render_mt5_report, render_settings, sector_momentum, stats,
)

st.set_page_config(page_title="Backtest ETF", page_icon="📊", layout="wide")
settings = render_settings()

st.title("📊 Backtest: Sektor-ETF-Rotation")
st.caption("Jegadeesh/Titman (1993) · Sarwar/Mateus/Todorovic, SSRN #2987819 — Literaturwerte, nicht optimiert")

monthly, sector_prices, spy_ret, momentum, fwd_ret, dates = sector_momentum(settings)
strat_ret, basket_log = backtest_etf_rotation(momentum, fwd_ret, dates, settings["top_n"], settings["hold"])
bh_ret = sector_prices.pct_change().mean(axis=1).dropna()

if strat_ret.empty:
    st.error("Keine Backtest-Ergebnisse fuer diese Parameter (Top-N zu hoch oder Zeitraum/Lookback zu knapp). "
             "Werte in der Sidebar reduzieren.")
    st.stop()

s_strat = stats(strat_ret, spy_ret)
s_bh = stats(bh_ret, spy_ret)
s_spy = stats(spy_ret, spy_ret)

capital = settings["capital"]
st.caption(f"Startkapital: {capital:,.0f} (in der Sidebar aenderbar)")

col1, col2 = st.columns(2)
with col1:
    render_mt5_report(strat_ret, capital, "Sektor-ETF-Rotation", bench=spy_ret)
with col2:
    render_mt5_report(bh_ret, capital, "Equal-Weight Buy&Hold", bench=spy_ret)

fig = go.Figure()
fig.add_trace(go.Scatter(x=s_strat["equity"].index, y=equity_in_capital(s_strat, capital), name="Sektor-ETF-Rotation", line=dict(width=3)))
fig.add_trace(go.Scatter(x=s_bh["equity"].index, y=equity_in_capital(s_bh, capital), name="Equal-Weight Buy&Hold", line=dict(width=2, dash="dot")))
fig.add_trace(go.Scatter(x=s_spy["equity"].index, y=equity_in_capital(s_spy, capital), name="S&P 500 (SPY)", line=dict(width=2, color="gray", dash="dashdot")))
fig.update_layout(title=f"Kapitalentwicklung (Start: {capital:,.0f})", yaxis_title="Kapital", template="plotly_dark", height=450)
st.plotly_chart(fig, width="stretch")

st.subheader("Monatliche Renditen")
render_monthly_returns_pager({"Sektor-ETF-Rotation": strat_ret, "Equal-Weight Buy&Hold": bh_ret}, key="etf_page")

st.subheader("Gekaufte Sektor-ETFs je Rotation")
log_df = basket_log_to_df(basket_log, SECTOR_ETFS).sort_values("Datum", ascending=False)
log_df["Momentum"] = log_df["Momentum"] * 100
st.caption(f"{log_df['Datum'].nunique()} Rotationen im Backtest-Zeitraum, {len(log_df)} Positionen insgesamt.")
st.dataframe(
    log_df,
    width="stretch",
    hide_index=True,
    column_config={"Momentum": st.column_config.NumberColumn(format="%+.1f%%")},
)

st.caption("Keine Transaktionskosten/Slippage eingerechnet. Kurzer Testzeitraum = geringe statistische Signifikanz.")
