# app.py
"""Alex Bets - Gestor de surebets (arbitraje deportivo)."""

import streamlit as st

import database as db
from paginas import calculadora, dashboard, historial, oportunidades, registrar

st.set_page_config(page_title="Alex Bets", page_icon="💶", layout="wide")

st.markdown(
    """
    <style>
    /* Ajustes para pantallas pequeñas (móvil): menos aire alrededor,
       botones a todo el ancho para acertar mejor con el dedo, y ninguna
       columna se queda estrecha de más al apilarse. */
    @media (max-width: 640px) {
        .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
            padding-top: 2rem;
        }
        div[data-testid="stButton"] button,
        div[data-testid="stFormSubmitButton"] button {
            width: 100%;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.4rem;
        }
        div[data-testid="column"] {
            min-width: 100% !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


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

PAGINAS = {
    "🔭 Oportunidades": oportunidades,
    "📝 Registrar apuesta": registrar,
    "🧮 Calculadora": calculadora,
    "📜 Historial": historial,
    "📊 Dashboard": dashboard,
}

# Selector de página en vez de st.tabs(): con st.tabs(), Streamlit ejecuta el
# contenido de las 5 pestañas en cada interacción (no solo la visible), lo que
# hacía que cualquier clic en una pantalla recalculase también las otras 4 por
# detrás. Con un selector normal, solo se ejecuta la página elegida.
nombre_pagina = st.radio(
    "Navegación", options=list(PAGINAS.keys()), horizontal=True, label_visibility="collapsed",
)

PAGINAS[nombre_pagina].render()
