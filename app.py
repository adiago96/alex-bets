# app.py
"""Alex Bets - Gestor de surebets (arbitraje deportivo)."""

import streamlit as st

import database as db
from paginas import dashboard, registrar

st.set_page_config(page_title="Alex Bets", page_icon="💶", layout="wide")

db.init_db()

st.title("💶 Alex Bets — Gestor de Surebets")

tab_registrar, tab_dashboard = st.tabs(["📝 Registrar apuesta", "📊 Dashboard"])

with tab_registrar:
    registrar.render()

with tab_dashboard:
    dashboard.render()
