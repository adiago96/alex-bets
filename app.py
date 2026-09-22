# app.py
"""Alex Bets - Gestor de surebets (arbitraje deportivo)."""

import streamlit as st

import database as db
from paginas import calculadora, dashboard, historial, oportunidades, registrar

st.set_page_config(page_title="Alex Bets", page_icon="💶", layout="wide")


def _acceso_autorizado() -> bool:
    """Pantalla de contraseña antes de mostrar nada de la app. Si no hay
    APP_PASSWORD configurada en secrets (uso solo en local), no bloquea."""
    password_correcta = st.secrets.get("APP_PASSWORD")
    if not password_correcta:
        return True
    if st.session_state.get("autorizado"):
        return True

    st.title("💶 Alex Bets")
    intento = st.text_input("Contraseña", type="password", key="password_acceso")
    if st.button("Entrar"):
        if intento == password_correcta:
            st.session_state.autorizado = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    return False


if not _acceso_autorizado():
    st.stop()

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
