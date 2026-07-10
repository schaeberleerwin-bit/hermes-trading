@echo off
cd /d C:\Users\schae\hermes-trading
set VIRTUAL_ENV=
set UV_PROJECT_ENVIRONMENT=.venv
uv run python -m hermes_trading.run >> C:\Users\schae\hermes-trading\state\worker.log 2>&1
