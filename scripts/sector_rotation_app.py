"""Dashboard: Sector Momentum Rotational System — Home/Uebersicht.

Basis-Strategie (validiert) aus Jegadeesh/Titman ("Returns to Buying Winners and
Selling Losers", 1993) und Sarwar/Mateus/Todorovic (SSRN #2987819).

Unterseiten (siehe Navigation links):
  1 Signal          -- was jetzt gekauft werden soll (ETF & Einzelaktien), Kapital-Rechner
  2 Backtest ETF     -- validierte Sektor-ETF-Rotation: Kennzahlen, Chart, Alpha/Beta
  3 Backtest Aktien   -- experimentelle Einzelaktien-Variante, mit Bias-Warnhinweis

Start: streamlit run scripts/sector_rotation_app.py
"""

import streamlit as st

from sector_rotation_lib import render_settings

st.set_page_config(page_title="Sector Rotation", page_icon="📈", layout="wide")
render_settings()

st.title("📈 Sector Momentum Rotation")
st.caption("Jegadeesh/Titman (1993) · Sarwar/Mateus/Todorovic, SSRN #2987819 — Standardwerte, nicht optimiert")

st.markdown("""
Diese App testet eine **Sektor-Rotations-Strategie**: jeden Monat werden die staerksten
SPDR-Sektor-ETFs nach 12-Monats-Momentum gekauft, gehalten, dann neu geranked.

**Navigation (links):**
- **🎯 Signal** — was du *jetzt* kaufen wuerdest, inkl. Stueckzahl-Rechner fuer dein Kapital
- **📊 Backtest ETF** — die literaturgestuetzte Original-Strategie auf ETF-Ebene
- **🧪 Backtest Aktien** — Erweiterung auf Einzelaktien innerhalb der Top-Sektoren (experimentell, Bias-Risiko)

Alle Einstellungen (Zeitraum, Lookback, Basket-Groesse, Haltedauer, Kapital) stehen in der
Sidebar und gelten seitenuebergreifend.
""")

st.info("Einstellungen links in der Sidebar setzen, dann zur gewuenschten Unterseite wechseln.")
