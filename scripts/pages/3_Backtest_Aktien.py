"""Seite: Backtest der Einzelaktien-Rotation (experimentelle Erweiterung)."""

import plotly.graph_objects as go
import streamlit as st

from sector_rotation_lib import (
    SECTOR_ETFS, backtest_etf_rotation, backtest_stock_rotation, contributed_total, equity_in_capital,
    equity_with_contributions, load_sp500_sector_map, load_stock_history, render_monthly_returns_pager,
    render_mt5_report, render_settings, sector_momentum, stats, stock_basket_log_to_df, stock_high_proximity,
    stock_volatility,
)

st.set_page_config(page_title="Backtest Aktien", page_icon="🧪", layout="wide")
settings = render_settings()

st.title("🧪 Backtest: Einzelaktien-Rotation")
st.warning("Experimentell, NICHT aus der Literatur validiert. Nutzt die HEUTIGE GICS-Sektor-Zuordnung "
           "rueckwirkend im Backtest (Lookahead-Bias) — Ergebnis als Richtwert lesen, nicht als "
           "belastbare Kennzahl wie bei der ETF-Strategie.")

monthly, sector_prices, spy_ret, momentum, fwd_ret, dates = sector_momentum(settings)

sector_map = load_sp500_sector_map()
with st.spinner("Lade Kurs-Historie fuer S&P-500-Einzelaktien (einmalig, danach 24h gecacht)..."):
    all_stocks = tuple(sector_map.index)
    stock_monthly = load_stock_history(all_stocks, settings["start_date"], settings["end_date"])
stock_momentum = stock_monthly.pct_change(settings["lookback"])
stock_fwd_ret = stock_monthly.pct_change().shift(-1)
stock_vol = stock_volatility(stock_monthly, settings["lookback"])
stock_high = stock_high_proximity(stock_monthly, settings["lookback"])

st.caption(f"Aktien-Auswahl-Methode: **{settings['stock_pick_method']}** (in der Sidebar aenderbar)")

stock_ret, stock_basket_log = backtest_stock_rotation(
    momentum, dates, settings["top_n"], settings["hold"], sector_map,
    stock_momentum, stock_fwd_ret, settings["stocks_per_sector"],
    method=settings["stock_pick_method"], stock_vol=stock_vol, stock_high=stock_high,
)
etf_ret, _ = backtest_etf_rotation(momentum, fwd_ret, dates, settings["top_n"], settings["hold"])

if stock_ret.empty or etf_ret.empty:
    st.error("Keine Backtest-Ergebnisse fuer diese Parameter (Top-N zu hoch oder Zeitraum/Lookback zu knapp). "
             "Werte in der Sidebar reduzieren.")
    st.stop()

s_stock = stats(stock_ret, spy_ret)
s_etf = stats(etf_ret, spy_ret)
s_spy = stats(spy_ret, spy_ret)

capital = settings["capital"]
st.caption(f"Startkapital: {capital:,.0f} (in der Sidebar aenderbar)")

col1, col2 = st.columns(2)
with col1:
    render_mt5_report(stock_ret, capital, "Einzelaktien-Rotation", bench=spy_ret)
with col2:
    render_mt5_report(etf_ret, capital, "Sektor-ETF-Rotation (Vergleich)", bench=spy_ret)

fig = go.Figure()
fig.add_trace(go.Scatter(x=s_stock["equity"].index, y=equity_in_capital(s_stock, capital), name="Einzelaktien-Rotation", line=dict(width=3, dash="dash")))
fig.add_trace(go.Scatter(x=s_etf["equity"].index, y=equity_in_capital(s_etf, capital), name="Sektor-ETF-Rotation", line=dict(width=2, dash="dot")))
fig.add_trace(go.Scatter(x=s_spy["equity"].index, y=equity_in_capital(s_spy, capital), name="S&P 500 (SPY)", line=dict(width=2, color="gray", dash="dashdot")))
fig.update_layout(title=f"Kapitalentwicklung (Start: {capital:,.0f})", yaxis_title="Kapital", template="plotly_dark", height=450)
st.plotly_chart(fig, width="stretch")

st.subheader("Monatliche Renditen")
render_monthly_returns_pager({"Einzelaktien-Rotation": stock_ret, "Sektor-ETF-Rotation": etf_ret}, key="stock_page")

st.caption("Keine Transaktionskosten/Slippage eingerechnet — bei mehr Einzelpositionen real staerker ins Gewicht "
           "fallend als bei der ETF-Variante.")

st.subheader("Gekaufte Einzelaktien je Rotation")
stock_log_df = stock_basket_log_to_df(stock_basket_log, SECTOR_ETFS, sector_map).sort_values("Datum", ascending=False)
st.caption(f"{stock_log_df['Datum'].nunique()} Rotationen im Backtest-Zeitraum, {len(stock_log_df)} Positionen insgesamt.")
st.dataframe(
    stock_log_df,
    width="stretch",
    hide_index=True,
    column_config={"Score": st.column_config.NumberColumn(format="%.3f")},
)

st.divider()
st.subheader("💰 Sparplan-Vergleich (monatliche Nachzahlung)")
st.caption("Separate Simulation: wie waere die Kapitalentwicklung, wenn zusaetzlich zum Startkapital "
           "jeden Monat ein fester Betrag eingezahlt und mitinvestiert wird? Vergleicht alle drei Strategien "
           "(Einzelaktien-Rotation, Sektor-ETF-Rotation, S&P 500) ueber denselben Zeitraum.")
monthly_contribution = st.number_input(
    "Monatliche Einzahlung", min_value=0.0, value=1000.0, step=100.0, key="sparplan_contribution",
)
if monthly_contribution > 0:
    contribution_per_period = monthly_contribution * settings["hold"]

    sparplan_strategies = {
        "Einzelaktien-Rotation": stock_ret,
        "Sektor-ETF-Rotation": etf_ret,
        "S&P 500 (SPY)": spy_ret,
    }
    stats_by_strategy = {"Einzelaktien-Rotation": s_stock, "Sektor-ETF-Rotation": s_etf, "S&P 500 (SPY)": s_spy}

    fig_sp = go.Figure()
    dash_by_strategy = {"Einzelaktien-Rotation": "solid", "Sektor-ETF-Rotation": "dot", "S&P 500 (SPY)": "dashdot"}
    contributed = None
    cols = st.columns(len(sparplan_strategies))
    for col, (name, ret) in zip(cols, sparplan_strategies.items()):
        with_sparplan = equity_with_contributions(ret, capital, contribution_per_period)
        contributed = contributed_total(ret, capital, contribution_per_period)
        ohne_sparplan = equity_in_capital(stats_by_strategy[name], capital).iloc[-1]

        endkapital = with_sparplan.iloc[-1]
        eingezahlt = contributed.iloc[-1]
        gewinn = endkapital - eingezahlt

        with col:
            st.markdown(f"**{name}**")
            st.metric("Kontostand am Ende", f"{endkapital:,.0f}", help="Inkl. aller Einzahlungen, mitinvestiert")
            st.metric("Ohne Einzahlungen", f"{ohne_sparplan:,.0f}", help="Reine Strategie-Performance, nur Startkapital")
            st.metric("Gewinn ggü. Einzahlungen", f"{gewinn:+,.0f}")

        fig_sp.add_trace(go.Scatter(x=with_sparplan.index, y=with_sparplan, name=name,
                                     line=dict(width=2.5, dash=dash_by_strategy[name])))

    if contributed is not None:
        fig_sp.add_trace(go.Scatter(x=contributed.index, y=contributed, name="Eingezahlt (ohne Rendite)",
                                     line=dict(width=1.5, dash="dash", color="gray")))
    fig_sp.update_layout(title="Kapitalentwicklung mit Sparplan", yaxis_title="Kapital", template="plotly_dark", height=450)
    st.plotly_chart(fig_sp, width="stretch")
else:
    st.info("Monatliche Einzahlung auf 0 — kein Sparplan-Vergleich.")
