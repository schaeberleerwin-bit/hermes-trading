"""Seite: Aktuelles Kauf-Signal + Kapital-Rechner."""

import streamlit as st

from sector_rotation_lib import (
    SECTOR_ETFS, buy_position, load_last_price, load_portfolio, load_sp500_sector_map, load_stock_history,
    load_usd_eur_rate, pick_stocks, render_portfolio, render_settings, sector_momentum, stock_high_proximity,
    stock_volatility,
)

st.set_page_config(page_title="Signal", page_icon="🎯", layout="wide")
settings = render_settings()

st.title("🎯 Aktuelles Signal — jetzt kaufen/halten")

portfolio = load_portfolio(settings["capital"])

usd_eur = load_usd_eur_rate()
st.caption(f"Kurse in € umgerechnet (Kurs: 1 USD = {usd_eur:.4f} EUR, Stand: aktuell, stuendlich aktualisiert). "
           "US-Aktien/Sektor-ETFs werden von yfinance in USD geliefert.")

monthly, sector_prices, spy_ret, momentum, fwd_ret, dates = sector_momentum(settings)
latest_date = momentum.index[-1]
latest_scores = momentum.loc[latest_date].dropna().sort_values(ascending=False)
current_sectors = latest_scores.head(settings["top_n"])

st.caption(f"Ranking-Stichtag: {latest_date.date()} ({settings['lookback']}M-Momentum) · "
           f"Top-{settings['top_n']}-Sektoren: {', '.join(current_sectors.index)}")

sector_map = load_sp500_sector_map()
with st.spinner("Lade Kurs-Historie fuer S&P-500-Einzelaktien (einmalig, danach 24h gecacht)..."):
    all_stocks = tuple(sector_map.index)
    stock_monthly = load_stock_history(all_stocks, settings["start_date"], settings["end_date"])
stock_momentum = stock_monthly.pct_change(settings["lookback"])
stock_vol = stock_volatility(stock_monthly, settings["lookback"])
stock_high = stock_high_proximity(stock_monthly, settings["lookback"])

tab_stocks, tab_etf = st.tabs(["Einzelaktien-Basket", "Sektor-ETF-Basket"])

with tab_stocks:
    current_stock_picks = pick_stocks(latest_date, current_sectors.index.tolist(), sector_map,
                                       stock_momentum, settings["stocks_per_sector"],
                                       method=settings["stock_pick_method"],
                                       etf_momentum=momentum.loc[latest_date], stock_vol=stock_vol,
                                       stock_high=stock_high)
    live_prices = load_last_price(tuple(current_stock_picks.index)) * usd_eur
    n_positions = len(current_stock_picks)
    alloc = settings["capital"] / n_positions if n_positions else 0

    cols = st.columns(min(n_positions, 5)) if n_positions else []
    total_used = 0.0
    for i, (sym, score) in enumerate(current_stock_picks.items()):
        price = float(live_prices[sym])
        shares = int(alloc // price)
        used = shares * price
        total_used += used
        with cols[i % len(cols)]:
            etf = sector_map.loc[sym, "ETF"]
            stock_name = sector_map.loc[sym, "Name"]
            st.metric(sym, f"{score:+.1%}", help=f"{settings['lookback']}-Monats-Momentum · Sektor {etf} ({SECTOR_ETFS[etf]})")
            st.caption(stock_name)
            st.write(f"Kurs: **{price:.2f} €**")
            st.write(f"→ **{shares} Stueck** ({used:,.0f} €)")
            if st.button(f"💰 Kaufen {sym}", key=f"buy_stock_{sym}", disabled=shares <= 0):
                buy_position(portfolio, sym, shares, price, sector=SECTOR_ETFS[etf], name=stock_name)
                st.success(f"Simuliert gekauft: {shares}x {sym} ({stock_name}) @ {price:.2f} €")
                st.rerun()

    st.caption(f"Nicht investierter Rest (Rundungsdifferenz): {settings['capital'] - total_used:,.2f} € "
               f"· {n_positions} Positionen a {alloc:,.0f} € Budget")
    st.warning("Nutzt die HEUTIGE Sektor-Zuordnung — fuer die Live-Empfehlung unproblematisch, "
               "siehe Seite 'Backtest Aktien' fuer den Bias-Hinweis im historischen Vergleich.")

with tab_etf:
    live_prices_etf = load_last_price(tuple(current_sectors.index)) * usd_eur
    alloc_etf = settings["capital"] / settings["top_n"]
    cols = st.columns(settings["top_n"])
    total_used_etf = 0.0
    for col, (sym, score) in zip(cols, current_sectors.items()):
        price = float(live_prices_etf[sym])
        shares = int(alloc_etf // price)
        used = shares * price
        total_used_etf += used
        with col:
            st.metric(f"{sym} — {SECTOR_ETFS[sym]}", f"{score:+.1%}", help=f"{settings['lookback']}-Monats-Rendite")
            st.write(f"Kurs: **{price:.2f} €**")
            st.write(f"→ **{shares} Stueck** ({used:,.0f} €)")
            if st.button(f"💰 Kaufen {sym}", key=f"buy_etf_{sym}", disabled=shares <= 0):
                buy_position(portfolio, sym, shares, price, sector=SECTOR_ETFS[sym], name=SECTOR_ETFS[sym])
                st.success(f"Simuliert gekauft: {shares}x {sym} ({SECTOR_ETFS[sym]}) @ {price:.2f} €")
                st.rerun()
    st.caption(f"Nicht investierter Rest (Rundungsdifferenz): {settings['capital'] - total_used_etf:,.2f} €")

    with st.expander("Vollstaendiges Ranking aller Sektoren"):
        rank_df = latest_scores.rename("Momentum").to_frame()
        rank_df.index.name = "ETF"
        rank_df["Name"] = [SECTOR_ETFS[s] for s in rank_df.index]
        rank_df["Top-Sektor"] = rank_df.index.isin(current_sectors.index)
        st.dataframe(rank_df[["Name", "Momentum", "Top-Sektor"]].style.format({"Momentum": "{:+.1%}"}), width="stretch")

st.divider()

# Fuer die Depot-Bewertung brauchen wir Live-Preise fuer ALLE offenen Positionen, nicht nur die
# aktuell im Signal empfohlenen Symbole (alte Positionen aus frueheren Rotationen koennen abweichen).
portfolio_symbols = set(portfolio["positions"].keys()) | set(current_stock_picks.index) | set(current_sectors.index)
combined_live_prices = (load_last_price(tuple(sorted(portfolio_symbols))) * usd_eur).to_dict() if portfolio_symbols else {}

# Sprechender Name je Symbol: Firmenname bei Aktien (sector_map), Sektorname bei ETFs (SECTOR_ETFS).
name_lookup = {**sector_map["Name"].to_dict(), **SECTOR_ETFS}

render_portfolio(portfolio, combined_live_prices, name_lookup=name_lookup)
