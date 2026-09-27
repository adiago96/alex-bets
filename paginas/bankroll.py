# paginas/bankroll.py
"""Pestaña de bankroll: líquido y dinero en juego por casa de apuestas.

A diferencia del resto de la app, aquí no se calcula nada a partir del
historial de apuestas: el líquido y el importe en juego de cada casa son
cifras que tú escribes y guardas directamente, porque solo tú sabes lo que de
verdad tienes en cada casa en cada momento. Así puedes corregir cualquier
desajuste sin tener que "engañar" al sistema con depósitos o retiradas
ficticias.
"""

import streamlit as st

import database as db

NUEVA_CASA = "+ Añadir nueva casa…"


def _mostrar_totales(casas):
    total_liquido = sum(c["liquido"] for c in casas)
    total_pendiente = sum(c["pendiente"] for c in casas)
    c1, c2, c3 = st.columns(3)
    c1.metric("Líquido total", f"{total_liquido:,.2f} €")
    c2.metric("En juego (total)", f"{total_pendiente:,.2f} €")
    c3.metric("Saldo total", f"{total_liquido + total_pendiente:,.2f} €")


def _tarjeta_casa(casa):
    nombre = casa["casa_apuestas"]
    with st.container(border=True):
        st.markdown(f"**{nombre}**")
        with st.form(f"form_bankroll_{nombre}"):
            col_a, col_b = st.columns(2)
            liquido = col_a.number_input(
                "Líquido (€)", value=float(casa["liquido"]), step=1.0, key=f"liq_{nombre}"
            )
            pendiente = col_b.number_input(
                "En juego (€)", value=float(casa["pendiente"]), step=1.0, key=f"pen_{nombre}"
            )
            if st.form_submit_button("Guardar", use_container_width=True):
                db.guardar_bankroll(nombre, liquido, pendiente)
                st.rerun()
        st.caption(f"Saldo total: {casa['liquido'] + casa['pendiente']:,.2f} €")


def _formulario_nueva_casa(nombres_existentes):
    st.subheader("Añadir casa de apuestas")
    with st.form("form_nueva_casa_bankroll", clear_on_submit=True):
        nombre = st.text_input("Nombre de la casa")
        col_a, col_b = st.columns(2)
        liquido_ini = col_a.number_input("Líquido inicial (€)", value=0.0, step=1.0)
        pendiente_ini = col_b.number_input("En juego inicial (€)", value=0.0, step=1.0)
        if st.form_submit_button("Añadir"):
            nombre = nombre.strip()
            if not nombre:
                st.error("Indica el nombre de la casa de apuestas.")
            elif nombre in nombres_existentes:
                st.error("Ya existe una casa con ese nombre; edítala arriba.")
            else:
                db.guardar_bankroll(nombre, liquido_ini, pendiente_ini)
                st.success(f"'{nombre}' añadida.")
                st.rerun()


def _eliminar_casa(nombres_existentes):
    with st.expander("Eliminar una casa del bankroll"):
        casa_a_borrar = st.selectbox("Casa", options=nombres_existentes, key="bankroll_casa_a_borrar")
        if st.button("🗑️ Eliminar", key="bankroll_btn_eliminar"):
            db.eliminar_bankroll_casa(casa_a_borrar)
            st.rerun()


def render():
    st.subheader("Bankroll por casa de apuestas")
    st.caption(
        "Líquido y en juego se editan a mano: escribe la cifra real que tienes ahora mismo "
        "en cada casa y pulsa Guardar. No se recalculan solos a partir de las apuestas, así "
        "que siempre puedes ajustarlos para que coincidan con la realidad."
    )

    casas = db.listar_bankroll()

    if not casas:
        st.info("Todavía no hay ninguna casa. Añade la primera abajo.")
    else:
        _mostrar_totales(casas)
        st.markdown("---")
        columnas = st.columns(2)
        for i, casa in enumerate(casas):
            with columnas[i % 2]:
                _tarjeta_casa(casa)

    st.markdown("---")
    nombres_existentes = [c["casa_apuestas"] for c in casas]
    _formulario_nueva_casa(nombres_existentes)
    if nombres_existentes:
        _eliminar_casa(nombres_existentes)
