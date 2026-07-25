# Hermes Trading Agent

**Selbstlernender Trading-Agent im Paper-Mode mit Self-Reflection-Loop.**

## Konzept

```
┌────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐
│ Market │→ │  Strategie │→ │  Paper-    │→ │  Reflect &  │
│ Data   │   │  Loop      │   │  Trade     │   │  Score      │
└────────┘   └───────────┘   └───────────┘   └───────────┘
                                                     │
                                          zurück in strategy.yaml
```

Simuliert Markt-Making-Strategien im **reinen Paper-Mode** (kein echtes Geld), bewertet die eigene Performance nach jedem Zyklus (`score.py`) und passt Hypothesen automatisiert an (`reflect.py`), bevor der nächste Zyklus startet. Konfiguration und Trade-Historie liegen getrennt im [hermes-trading-config](https://github.com/schaeberleerwin-bit/hermes-trading-config)-Repo.

## Features

- ✅ Self-Reflection-Loop: Hypothesen generieren, testen, bewerten, verfeinern
- ✅ Backtesting-Tools: Faktor-, Trend-, Sektor-Rotations- und Monte-Carlo-Backtests
- ✅ Streamlit-Dashboards zur Auswertung
- ✅ Docker-Deployment
- ⚠️ **Ausschließlich Paper-Mode** – kein Live-Trading ohne explizite Freigabe

## Tech Stack

| Schicht | Technologie |
|---|---|
| Sprache | Python 3.11+ |
| Marktdaten | ccxt, yfinance |
| Analyse | pandas, numpy |
| Visualisierung | plotly, streamlit |
| Build | hatchling, uv |

## Setup

```bash
uv sync
python -m hermes_trading.run
```

## Ordnerstruktur

```
hermes_trading/
├── loop.py        # Haupt-Trading-Loop
├── reflect.py      # Self-Reflection nach jedem Zyklus
├── score.py        # Performance-Bewertung
├── adapters/        # Markt-/Exchange-Adapter
└── strategies/       # Handelsstrategien

scripts/
├── factor_backtest.py
├── trend_backtest.py
├── sector_rotation_app.py   # Streamlit-Dashboard
└── monte_carlo_optimize.py
```
