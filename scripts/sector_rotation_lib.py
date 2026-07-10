"""Gemeinsame Logik fuer das Sector-Rotation-Dashboard (von allen Seiten importiert)."""

import datetime
import io
import json
import pathlib

import httpx
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

MONTHS_DE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

SECTOR_ETFS = {
    "XLK": "Technologie", "XLF": "Finanzen", "XLV": "Gesundheit", "XLY": "Konsum zyklisch",
    "XLP": "Konsum defensiv", "XLE": "Energie", "XLI": "Industrie", "XLB": "Rohstoffe",
    "XLU": "Versorger", "XLRE": "Immobilien", "XLC": "Kommunikation",
}

GICS_TO_ETF = {
    "Information Technology": "XLK", "Financials": "XLF", "Health Care": "XLV",
    "Consumer Discretionary": "XLY", "Consumer Staples": "XLP", "Energy": "XLE",
    "Industrials": "XLI", "Materials": "XLB", "Utilities": "XLU",
    "Real Estate": "XLRE", "Communication Services": "XLC",
}


SETTINGS_FILE = pathlib.Path(__file__).resolve().parent.parent / "state" / "dashboard_settings.json"


def _load_persisted_settings() -> dict:
    """Zuletzt gespeicherte Sidebar-Einstellungen von Platte -- Vorgabewerte fuer eine NEUE Session.
    Innerhalb einer laufenden Session hat Streamlits eigener session_state (ueber die widget-`key`s) Vorrang."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_persisted_settings(settings: dict) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    to_save = {**settings, "start_date": settings["start_date"].isoformat(), "end_date": settings["end_date"].isoformat()}
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2)


def render_settings() -> dict:
    """Einstellungen in der Sidebar. Gleiche Keys auf jeder Seite -> bleiben beim Wechseln erhalten.
    Werden ausserdem dauerhaft in eine Datei gespeichert, damit sie auch nach einem Neustart der App
    bzw. in einer neuen Browser-Session als Vorgabe geladen werden (statt immer auf die Hardcoded-Defaults
    zurueckzufallen)."""
    today = datetime.date.today()
    saved = _load_persisted_settings()
    with st.sidebar:
        st.header("Einstellungen")
        if "start_date" in saved and "end_date" in saved:
            default_range = (datetime.date.fromisoformat(saved["start_date"]),
                              datetime.date.fromisoformat(saved["end_date"]))
        else:
            default_range = (today.replace(year=today.year - 10), today)
        date_range = st.date_input(
            "Backtest-Zeitraum", value=default_range,
            min_value=today.replace(year=today.year - 20), max_value=today, key="date_range",
        )
        if len(date_range) != 2:
            st.stop()  # Nutzer waehlt gerade erst das zweite Datum
        start_date, end_date = date_range
        lookback = st.slider("Momentum-Lookback (Monate)", 3, 24, saved.get("lookback", 12), key="lookback")
        top_n = st.slider("Anzahl Top-Sektoren", 1, 5, saved.get("top_n", 3), key="top_n")
        hold = st.slider("Haltedauer (Monate)", 1, 6, saved.get("hold", 1), key="hold")
        stocks_per_sector = st.slider("Aktien pro Top-Sektor", 1, 10, saved.get("stocks_per_sector", 3),
                                       key="stocks_per_sector")
        st.caption("Standard: 12 / 3 / 1 (Literaturwerte, ETF-Ebene). Aendern = eigener Test.")
        method_keys = list(STOCK_PICK_METHODS.keys())
        default_method = saved.get("stock_pick_method", "residual")
        stock_pick_method = st.radio(
            "Aktien-Auswahl-Methode", method_keys,
            index=method_keys.index(default_method) if default_method in method_keys else 0,
            format_func=lambda m: STOCK_PICK_METHODS[m],
            key="stock_pick_method",
            help="Residual = Staerke relativ zum eigenen Sektor / Volatilitaet (Blitz et al.). "
                 "52-Wochen-Hoch = George & Hwang. Low-Volatility = Ang et al. (defensiv). "
                 "Rohes Momentum = einfachste, aber am wenigsten robuste Variante.",
        )
        capital = st.number_input("Verfuegbares Kapital (EUR)", min_value=0.0,
                                   value=saved.get("capital", 10000.0), step=500.0, key="capital")
        st.caption("Alle Einstellungen werden automatisch dauerhaft gespeichert (auch fuer neue Sessions).")
    result = dict(start_date=start_date, end_date=end_date, lookback=lookback, top_n=top_n, hold=hold,
                  stocks_per_sector=stocks_per_sector, stock_pick_method=stock_pick_method, capital=capital)
    _save_persisted_settings(result)
    return result


@st.cache_data(ttl=3600)
def load_prices(start_date: datetime.date, end_date: datetime.date) -> pd.DataFrame:
    raw = yf.download(list(SECTOR_ETFS.keys()) + ["SPY"], start=start_date, end=end_date, interval="1mo",
                       auto_adjust=True, progress=False)["Close"]
    return raw.resample("ME").last().dropna(how="all")


@st.cache_data(ttl=3600)
def load_last_price(symbols: tuple) -> pd.Series:
    last = yf.download(list(symbols), period="5d", interval="1d", auto_adjust=True, progress=False)["Close"]
    return last.iloc[-1]


@st.cache_data(ttl=3600)
def load_usd_eur_rate() -> float:
    """Aktueller USD->EUR Wechselkurs (wie viele EUR fuer 1 USD). US-Aktien/Sektor-ETFs werden von
    yfinance in USD geliefert -- damit lassen sich Kurse fuers Dashboard in EUR umrechnen."""
    try:
        raw = yf.download("USDEUR=X", period="5d", interval="1d", auto_adjust=True, progress=False)["Close"]
        return float(raw.squeeze().iloc[-1])
    except Exception:
        return 1.0  # Fallback: keine Umrechnung, falls der FX-Kurs nicht geladen werden kann


@st.cache_data(ttl=86400)
def load_sp500_sector_map() -> pd.DataFrame:
    r = httpx.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                  headers={"User-Agent": "Mozilla/5.0 research-script contact:schaeberle.erwin@gmail.com"},
                  timeout=20, follow_redirects=True)
    df = pd.read_html(io.StringIO(r.text))[0][["Symbol", "Security", "GICS Sector"]]
    df["Symbol"] = df["Symbol"].str.replace(".", "-", regex=False)
    df["ETF"] = df["GICS Sector"].map(GICS_TO_ETF)
    df = df.rename(columns={"Security": "Name"})
    return df.set_index("Symbol")


@st.cache_data(ttl=86400)
def load_stock_history(symbols: tuple, start_date: datetime.date, end_date: datetime.date) -> pd.DataFrame:
    raw = yf.download(list(symbols), start=start_date, end=end_date, interval="1mo",
                       auto_adjust=True, progress=False)["Close"]
    return raw.resample("ME").last()


def sector_momentum(settings: dict):
    """Liefert (monthly, sector_prices, spy_ret, momentum, fwd_ret, dates)."""
    monthly = load_prices(settings["start_date"], settings["end_date"])
    sector_prices = monthly[list(SECTOR_ETFS.keys())]
    spy_ret = monthly["SPY"].pct_change().dropna()
    momentum = sector_prices.pct_change(settings["lookback"])
    fwd_ret = sector_prices.pct_change().shift(-1)
    dates = momentum.index[settings["lookback"]:-1]
    return monthly, sector_prices, spy_ret, momentum, fwd_ret, dates


STOCK_PICK_METHODS = {
    "residual": "Residual-Momentum + risikoadjustiert (empfohlen)",
    "raw": "Rohes Momentum",
    "52w_high": "Naehe zum 52-Wochen-Hoch",
    "low_vol": "Low-Volatility (defensiv)",
}


def stock_volatility(stock_monthly: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Rollierende Volatilitaet (Std. der Monatsrenditen) je Aktie -- fuer Risiko-Adjustierung."""
    return stock_monthly.pct_change().rolling(lookback).std()


def stock_high_proximity(stock_monthly: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Kurs / rollierendes Hoch der letzten `lookback` Monate -- 1.0 = auf Jahreshoch."""
    return stock_monthly / stock_monthly.rolling(lookback).max()


def pick_stocks(date, top_etfs: list[str], sector_map: pd.DataFrame, stock_momentum: pd.DataFrame,
                stocks_per_sector: int, method: str = "residual", etf_momentum: pd.Series = None,
                stock_vol: pd.DataFrame = None, stock_high: pd.DataFrame = None) -> pd.Series:
    """Beste `stocks_per_sector` Aktien je Top-Sektor am gegebenen Stichtag.

    method="raw": reines 12M-Momentum-Ranking (kann volatile Sektor-Mitlaeufer bevorzugen).
    method="residual": (Aktien-Momentum - Sektor-ETF-Momentum) / Aktien-Volatilitaet.
        Belohnt Aktien, die STAERKER sind als ihr eigener Sektor, risikoadjustiert --
        Blitz et al. "Residual Momentum" / Barroso & Santa-Clara "Momentum has its Moments".
    method="52w_high": Kurs nahe am rollierenden Hoch -- George & Hwang,
        "The 52-Week High and Momentum Investing".
    method="low_vol": niedrigste Volatilitaet zuerst -- Ang et al.,
        "The Cross-Section of Volatility and Expected Returns" (defensive Anomalie).
    Rueckgabe: Series indiziert nach Symbol, Werte = Rohmomentum (fuer Anzeige), Reihenfolge = Ranking.
    """
    picks = {}
    for etf in top_etfs:
        members = stock_momentum.columns.intersection(sector_map.index[sector_map["ETF"] == etf])
        mom = stock_momentum.loc[date, members].dropna()

        if method == "raw":
            score = mom
        elif method == "52w_high":
            score = stock_high.loc[date, mom.index].dropna()
        elif method == "low_vol":
            vol = stock_vol.loc[date, mom.index].dropna()
            score = -vol
        else:  # residual
            vol = stock_vol.loc[date, mom.index]
            vol = vol[vol > 0]
            score = (mom[vol.index] - etf_momentum[etf]) / vol

        top_syms = score.dropna().sort_values(ascending=False).head(stocks_per_sector).index
        picks.update(mom.loc[top_syms].to_dict())
    return pd.Series(picks).sort_values(ascending=False)


def backtest_etf_rotation(momentum: pd.DataFrame, fwd_ret: pd.DataFrame, dates, top_n: int, hold: int):
    """(strat_ret Series, basket_log Liste von (datum, basket, scores))"""
    returns, ret_dates, log = [], [], []
    for i in range(0, len(dates), hold):
        date = dates[i]
        scores = momentum.loc[date].dropna()
        if len(scores) < top_n:
            continue
        basket = scores.sort_values(ascending=False).head(top_n).index.tolist()
        for h in range(hold):
            idx = dates.get_loc(date) + h
            if idx >= len(dates):
                break
            d = dates[idx]
            returns.append(fwd_ret.loc[d, basket].mean())
            ret_dates.append(d)
        log.append((date.date(), basket, scores[basket].round(3).to_dict()))
    return pd.Series(returns, index=pd.DatetimeIndex(ret_dates)).dropna(), log


def backtest_stock_rotation(momentum: pd.DataFrame, dates, top_n: int, hold: int, sector_map: pd.DataFrame,
                             stock_momentum: pd.DataFrame, stock_fwd_ret: pd.DataFrame, stocks_per_sector: int,
                             method: str = "residual", stock_vol: pd.DataFrame = None,
                             stock_high: pd.DataFrame = None):
    """(stock_ret Series, basket_log Liste von (datum, top_etfs, picks-Series Symbol->Score))"""
    returns, ret_dates, log = [], [], []
    for i in range(0, len(dates), hold):
        date = dates[i]
        scores = momentum.loc[date].dropna()
        if len(scores) < top_n:
            continue
        top_etfs = scores.sort_values(ascending=False).head(top_n).index.tolist()
        picks = pick_stocks(date, top_etfs, sector_map, stock_momentum, stocks_per_sector,
                            method=method, etf_momentum=momentum.loc[date], stock_vol=stock_vol,
                            stock_high=stock_high)
        if picks.empty:
            continue
        for h in range(hold):
            idx = dates.get_loc(date) + h
            if idx >= len(dates):
                break
            d = dates[idx]
            returns.append(stock_fwd_ret.loc[d, picks.index].mean())
            ret_dates.append(d)
        log.append((date.date(), top_etfs, picks.round(3)))
    return pd.Series(returns, index=pd.DatetimeIndex(ret_dates)).dropna(), log


def basket_log_to_df(basket_log: list, sector_etfs: dict) -> pd.DataFrame:
    """ETF-Basket-Log (aus backtest_etf_rotation) in eine flache Tabelle: Datum, Symbol, Sektor, Momentum."""
    rows = []
    for date, basket, scores in basket_log:
        for sym in basket:
            rows.append({"Datum": date, "Symbol": sym, "Sektor": sector_etfs[sym], "Momentum": scores[sym]})
    return pd.DataFrame(rows)


def stock_basket_log_to_df(basket_log: list, sector_etfs: dict, sector_map: pd.DataFrame) -> pd.DataFrame:
    """Aktien-Basket-Log (aus backtest_stock_rotation) in eine flache Tabelle:
    Datum, Top-Sektoren, Aktie, Name, GICS-Sektor, Score."""
    rows = []
    for date, top_etfs, picks in basket_log:
        top_sectors = ", ".join(sector_etfs[e] for e in top_etfs)
        for sym, score in picks.items():
            name = sector_map.loc[sym, "Name"] if sym in sector_map.index else sym
            gics = sector_map.loc[sym, "GICS Sector"] if sym in sector_map.index else "?"
            rows.append({"Datum": date, "Top-Sektoren": top_sectors, "Aktie": sym, "Name": name,
                         "GICS-Sektor": gics, "Score": score})
    return pd.DataFrame(rows)


def stats(ret: pd.Series, bench: pd.Series, rf_annual: float = 0.04) -> dict:
    equity = (1 + ret).cumprod()
    total = equity.iloc[-1] - 1
    ann_vol = ret.std() * np.sqrt(12)
    sharpe = (ret.mean() * 12) / ann_vol if ann_vol > 0 else 0
    max_dd = (equity / equity.cummax() - 1).min()
    df = pd.concat([ret, bench], axis=1, join="inner").dropna()
    df.columns = ["strat", "bench"]
    rf_m = rf_annual / 12
    beta, alpha_m = np.polyfit(df["bench"] - rf_m, df["strat"] - rf_m, 1)
    alpha_ann = (1 + alpha_m) ** 12 - 1
    return {"Total Return": total, "Sharpe": sharpe, "Max Drawdown": max_dd,
            "Alpha p.a.": alpha_ann, "Beta": beta, "equity": equity}


def mt5_report(ret: pd.Series, capital: float) -> dict:
    """Kennzahlen im Format des MT5-Strategy-Tester-Reports.
    Jeder Monat = 1 'Trade' (Position wird laut Backtest-Logik monatlich neu bewertet)."""
    equity = capital * (1 + ret).cumprod()
    prev = pd.concat([pd.Series([capital]), equity]).reset_index(drop=True)
    profits = prev.diff().dropna().to_numpy()

    gross_profit = profits[profits > 0].sum()
    gross_loss = profits[profits < 0].sum()
    net_profit = gross_profit + gross_loss
    profit_factor = gross_profit / abs(gross_loss) if gross_loss != 0 else np.inf

    total_trades = len(profits)
    win_trades = int((profits > 0).sum())
    loss_trades = int((profits < 0).sum())

    running_max = equity.cummax()
    dd_abs = float((running_max - equity).max())
    dd_pct = float((equity / running_max - 1).min()) * -1
    recovery_factor = net_profit / dd_abs if dd_abs > 0 else np.inf
    sharpe = (ret.mean() * 12) / (ret.std() * np.sqrt(12)) if ret.std() > 0 else 0

    max_consec_wins = max_consec_losses = 0
    cur_wins = cur_losses = 0
    for p in profits:
        if p > 0:
            cur_wins += 1
            cur_losses = 0
        elif p < 0:
            cur_losses += 1
            cur_wins = 0
        else:
            cur_wins = cur_losses = 0
        max_consec_wins = max(max_consec_wins, cur_wins)
        max_consec_losses = max(max_consec_losses, cur_losses)

    return {
        "Reingewinn": net_profit,
        "Bruttogewinn": gross_profit,
        "Bruttoverlust": gross_loss,
        "Profitfaktor": profit_factor,
        "Erwarteter Gewinn": net_profit / total_trades if total_trades else 0,
        "Sharpe Ratio": sharpe,
        "Wiederherstellungsfaktor": recovery_factor,
        "Maximaler Drawdown (absolut)": dd_abs,
        "Maximaler Drawdown (%)": dd_pct,
        "Gesamtzahl Trades": total_trades,
        "Gewinn-Trades (%)": win_trades / total_trades if total_trades else 0,
        "Verlust-Trades (%)": loss_trades / total_trades if total_trades else 0,
        "Groesster Gewinn-Trade": float(profits.max()) if total_trades else 0,
        "Groesster Verlust-Trade": float(profits.min()) if total_trades else 0,
        "Durchschnittlicher Gewinn-Trade": float(profits[profits > 0].mean()) if win_trades else 0,
        "Durchschnittlicher Verlust-Trade": float(profits[profits < 0].mean()) if loss_trades else 0,
        "Max. aufeinanderfolgende Gewinne": max_consec_wins,
        "Max. aufeinanderfolgende Verluste": max_consec_losses,
    }


def render_mt5_report(ret: pd.Series, capital: float, title: str, bench: pd.Series = None) -> None:
    r = mt5_report(ret, capital)
    st.subheader(title)
    rows = []
    if bench is not None:
        s = stats(ret, bench)
        rows += [("Alpha p.a. (vs. SPY)", f"{s['Alpha p.a.']:+.1%}"), ("Beta (vs. SPY)", f"{s['Beta']:.2f}")]
    rows += [
        ("Reingewinn", f"{r['Reingewinn']:,.2f}"),
        ("Bruttogewinn", f"{r['Bruttogewinn']:,.2f}"),
        ("Bruttoverlust", f"{r['Bruttoverlust']:,.2f}"),
        ("Profitfaktor", f"{r['Profitfaktor']:.2f}"),
        ("Erwarteter Gewinn", f"{r['Erwarteter Gewinn']:,.2f}"),
        ("Sharpe Ratio", f"{r['Sharpe Ratio']:.2f}"),
        ("Wiederherstellungsfaktor", f"{r['Wiederherstellungsfaktor']:.2f}"),
        ("Maximaler Drawdown (absolut)", f"{r['Maximaler Drawdown (absolut)']:,.2f}"),
        ("Maximaler Drawdown (%)", f"{r['Maximaler Drawdown (%)']:.1%}"),
        ("Gesamtzahl Trades", f"{r['Gesamtzahl Trades']}"),
        ("Gewinn-Trades (%)", f"{r['Gewinn-Trades (%)']:.1%}"),
        ("Verlust-Trades (%)", f"{r['Verlust-Trades (%)']:.1%}"),
        ("Groesster Gewinn-Trade", f"{r['Groesster Gewinn-Trade']:,.2f}"),
        ("Groesster Verlust-Trade", f"{r['Groesster Verlust-Trade']:,.2f}"),
        ("Durchschnittlicher Gewinn-Trade", f"{r['Durchschnittlicher Gewinn-Trade']:,.2f}"),
        ("Durchschnittlicher Verlust-Trade", f"{r['Durchschnittlicher Verlust-Trade']:,.2f}"),
        ("Max. aufeinanderfolgende Gewinne", f"{r['Max. aufeinanderfolgende Gewinne']}"),
        ("Max. aufeinanderfolgende Verluste", f"{r['Max. aufeinanderfolgende Verluste']}"),
    ]
    df = pd.DataFrame(rows, columns=["Kennzahl", "Wert"])
    st.dataframe(df, width="stretch", hide_index=True)


def render_monthly_returns_pager(returns: dict, key: str) -> None:
    """Balkendiagramm der Monatsrenditen (Jan-Dez), ein Jahr pro Seite, mit ◀ ▶ Paging."""
    all_years = sorted(set().union(*(set(r.index.year) for r in returns.values())))
    if not all_years:
        st.info("Keine Daten fuer Monatsrenditen vorhanden.")
        return

    idx_key = f"{key}_year_idx"
    if idx_key not in st.session_state:
        st.session_state[idx_key] = 0

    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        if st.button("◀ Vorheriges Jahr", key=f"{key}_prev", disabled=st.session_state[idx_key] <= 0):
            st.session_state[idx_key] -= 1
    with c3:
        if st.button("Nächstes Jahr ▶", key=f"{key}_next", disabled=st.session_state[idx_key] >= len(all_years) - 1):
            st.session_state[idx_key] += 1

    idx = st.session_state[idx_key]
    year = all_years[idx]
    with c2:
        st.markdown(f"<h4 style='text-align:center'>Jahr {idx + 1} von {len(all_years)} — {year}</h4>",
                    unsafe_allow_html=True)

    fig = go.Figure()
    for name, ret in returns.items():
        yearly = ret[ret.index.year == year]
        vals = [None] * 12
        for d, v in yearly.items():
            vals[d.month - 1] = v * 100
        fig.add_trace(go.Bar(x=MONTHS_DE, y=vals, name=name))
    fig.update_layout(barmode="group", yaxis_title="Rendite (%)", template="plotly_dark", height=350,
                       margin=dict(t=20))
    st.plotly_chart(fig, width="stretch", key=f"{key}_chart_{year}")


def show_metrics(s: dict, capital: float) -> None:
    """Kennzahlen-Kacheln inkl. Start-/Endkapital fuer eine Strategie."""
    endkapital = capital * (1 + s["Total Return"])
    m1, m2, m3 = st.columns(3)
    m1.metric("Endkapital", f"{endkapital:,.0f}", delta=f"{endkapital - capital:,.0f}")
    m2.metric("Total Return", f"{s['Total Return']:.1%}")
    m3.metric("Sharpe", f"{s['Sharpe']:.2f}")
    m4, m5, m6 = st.columns(3)
    m4.metric("Max Drawdown", f"{s['Max Drawdown']:.1%}")
    m5.metric("Alpha p.a.", f"{s['Alpha p.a.']:+.1%}")
    m6.metric("Beta", f"{s['Beta']:.2f}")


def equity_in_capital(s: dict, capital: float):
    """Equity-Kurve skaliert auf das Startkapital (statt normiert auf 1)."""
    return s["equity"] * capital


def equity_with_contributions(ret: pd.Series, capital: float, contribution_per_period: float) -> pd.Series:
    """Kapitalkurve, wenn zusaetzlich zum Startkapital jede Periode ein fester Betrag eingezahlt
    und sofort mitinvestiert wird (Sparplan). Einzahlung erfolgt vor Anwendung der Periodenrendite."""
    balance = capital
    values = []
    for r in ret:
        balance = (balance + contribution_per_period) * (1 + r)
        values.append(balance)
    return pd.Series(values, index=ret.index)


def contributed_total(ret: pd.Series, capital: float, contribution_per_period: float) -> pd.Series:
    """Reine Einzahlungssumme (Startkapital + Sparraten, ohne Rendite) zum Vergleich im Chart."""
    n = len(ret)
    return pd.Series([capital + (i + 1) * contribution_per_period for i in range(n)], index=ret.index)


# --- Paper-Trading (simuliertes Depot, KEINE Verbindung zu einem echten Broker) --------------------

PORTFOLIO_FILE = pathlib.Path(__file__).resolve().parent.parent / "state" / "paper_portfolio.json"


def load_portfolio(start_capital: float) -> dict:
    """Laedt das simulierte Depot von Platte, legt es beim ersten Aufruf mit Startkapital an."""
    if PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    portfolio = {"cash": start_capital, "start_capital": start_capital, "positions": {}, "history": []}
    save_portfolio(portfolio)
    return portfolio


def save_portfolio(portfolio: dict) -> None:
    PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, indent=2, default=str)


def buy_position(portfolio: dict, symbol: str, shares: int, price: float, sector: str = "", name: str = "") -> None:
    """Simulierter Kauf: Cash sinkt, Position wird angelegt/aufgestockt, Vorgang landet in der History."""
    if shares <= 0:
        return
    cost = shares * price
    pos = portfolio["positions"].setdefault(symbol, {"shares": 0, "avg_price": 0.0, "sector": sector, "name": name})
    total_shares = pos["shares"] + shares
    pos["avg_price"] = (pos["avg_price"] * pos["shares"] + cost) / total_shares
    pos["shares"] = total_shares
    pos["sector"] = sector or pos.get("sector", "")
    pos["name"] = name or pos.get("name", "")
    portfolio["cash"] -= cost
    portfolio["history"].append({
        "datum": datetime.datetime.now().isoformat(timespec="seconds"),
        "aktion": "Kauf", "symbol": symbol, "name": name, "stueck": shares, "preis": price, "betrag": -cost,
    })
    save_portfolio(portfolio)


def sell_position(portfolio: dict, symbol: str, shares: int, price: float) -> None:
    """Simulierter Verkauf (Teil- oder Komplettverkauf). Cash steigt, Position wird reduziert/geschlossen."""
    pos = portfolio["positions"].get(symbol)
    if pos is None or shares <= 0:
        return
    shares = min(shares, pos["shares"])
    proceeds = shares * price
    name = pos.get("name", "")
    pos["shares"] -= shares
    portfolio["cash"] += proceeds
    if pos["shares"] <= 0:
        del portfolio["positions"][symbol]
    portfolio["history"].append({
        "datum": datetime.datetime.now().isoformat(timespec="seconds"),
        "aktion": "Verkauf", "symbol": symbol, "name": name, "stueck": shares, "preis": price, "betrag": proceeds,
    })
    save_portfolio(portfolio)


def reset_portfolio(start_capital: float) -> dict:
    """Loescht alle simulierten Positionen/History und setzt das Depot auf Startkapital zurueck."""
    portfolio = {"cash": start_capital, "start_capital": start_capital, "positions": {}, "history": []}
    save_portfolio(portfolio)
    return portfolio


def render_portfolio(portfolio: dict, live_prices: dict, name_lookup: dict = None) -> None:
    """Depot-Uebersicht: Kontostand, offene Positionen mit Live-Bewertung, Gesamtvermoegen, History.
    name_lookup: optionales Symbol -> sprechender Name (Firmenname bei Aktien, Sektorname bei ETFs)."""
    st.subheader("💼 Mein simuliertes Depot")
    st.caption("Rein lokale Simulation — keine Verbindung zu einem echten Broker. Kaufen-Buttons auf dieser "
               "Seite bewegen nur diesen simulierten Kontostand.")

    name_lookup = name_lookup or {}
    positions = portfolio["positions"]
    pos_value = 0.0
    rows = []
    for sym, pos in positions.items():
        price = live_prices.get(sym)
        if price is None:
            continue
        value = pos["shares"] * price
        pos_value += value
        pnl = value - pos["shares"] * pos["avg_price"]
        pnl_pct = (price / pos["avg_price"] - 1) if pos["avg_price"] else 0
        rows.append({
            "Symbol": sym, "Name": pos.get("name") or name_lookup.get(sym, sym), "Sektor": pos.get("sector", ""),
            "Stueck": pos["shares"], "Ø-Kaufpreis": pos["avg_price"], "Kurs": price, "Wert": value,
            "G/V": pnl, "G/V %": pnl_pct * 100,
        })

    total_value = portfolio["cash"] + pos_value
    start_capital = portfolio.get("start_capital", portfolio["cash"])
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Kontostand (Cash)", f"{portfolio['cash']:,.2f} €")
    m2.metric("Positionswert", f"{pos_value:,.2f} €")
    m3.metric("Gesamtvermoegen", f"{total_value:,.2f} €", delta=f"{total_value - start_capital:+,.2f} €")
    m4.metric("Rendite ggue. Start", f"{(total_value / start_capital - 1):+.1%}" if start_capital else "–")

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(
            df, width="stretch", hide_index=True,
            column_config={
                "Ø-Kaufpreis": st.column_config.NumberColumn(format="%.2f"),
                "Kurs": st.column_config.NumberColumn(format="%.2f"),
                "Wert": st.column_config.NumberColumn(format="%.2f"),
                "G/V": st.column_config.NumberColumn(format="%+.2f"),
                "G/V %": st.column_config.NumberColumn(format="%+.1f%%"),
            },
        )
        st.markdown("**Position verkaufen (komplett):**")
        sell_cols = st.columns(min(len(rows), 6))
        for i, row in enumerate(rows):
            sym = row["Symbol"]
            with sell_cols[i % len(sell_cols)]:
                if st.button(f"Verkaufen {sym}", key=f"sell_{sym}"):
                    sell_position(portfolio, sym, positions[sym]["shares"], live_prices[sym])
                    st.rerun()
    else:
        st.info("Noch keine simulierten Positionen. Nutze die Kaufen-Buttons oben, um welche anzulegen.")

    with st.expander(f"Transaktions-History ({len(portfolio['history'])})"):
        if portfolio["history"]:
            hist_df = pd.DataFrame(list(reversed(portfolio["history"])))
            st.dataframe(hist_df, width="stretch", hide_index=True)
        else:
            st.caption("Noch keine simulierten Transaktionen.")

    if st.button("🗑️ Depot zuruecksetzen", key="reset_portfolio"):
        st.session_state["_confirm_reset"] = True
    if st.session_state.get("_confirm_reset"):
        st.warning("Wirklich alle simulierten Positionen und die History loeschen?")
        c1, c2 = st.columns(2)
        if c1.button("Ja, zuruecksetzen", key="confirm_reset_yes"):
            reset_portfolio(start_capital)
            st.session_state["_confirm_reset"] = False
            st.rerun()
        if c2.button("Abbrechen", key="confirm_reset_no"):
            st.session_state["_confirm_reset"] = False
            st.rerun()
