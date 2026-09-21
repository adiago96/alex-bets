# app.py
"""Alex Bets - Gestor de surebets (arbitraje deportivo)."""

import streamlit as st

import database as db
from paginas import calculadora, dashboard, historial, oportunidades, registrar

st.set_page_config(page_title="Alex Bets", page_icon="💶", layout="wide")

db.init_db()

st.title("💶 Alex Bets — Gestor de Surebets")

tab_oportunidades, tab_registrar, tab_calculadora, tab_historial, tab_dashboard = st.tabs(
    ["🔭 Oportunidades", "📝 Registrar apuesta", "🧮 Calculadora", "📜 Historial", "📊 Dashboard"]
)

with tab_oportunidades:
    oportunidades.render()

with tab_registrar:
    registrar.render()

with tab_calculadora:
    calculadora.render()

with tab_historial:
    historial.render()

with tab_dashboard:
    dashboard.render()
