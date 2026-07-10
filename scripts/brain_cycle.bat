@echo off
cd /d C:\Users\schae\hermes-trading
set VIRTUAL_ENV=
set UV_PROJECT_ENVIRONMENT=.venv
uv run python scripts\brain_cycle.py >> C:\Users\schae\hermes-trading\state\brain.log 2>&1
