@echo off
cd /d "%~dp0"
start "Alex Bets - Telegram" cmd /k python telegram_listener.py
start "Alex Bets - App" cmd /k python -m streamlit run app.py
