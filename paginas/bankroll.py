# paginas/bankroll.py
"""Pestaña de bankroll: líquido y dinero en juego por casa de apuestas.

El líquido de cada casa se mueve principalmente con los depósitos y
retiradas que registres en la sección de arriba: un depósito lo sube, una
retirada lo baja, al momento. El importe en juego (dinero metido en apuestas
abiertas) no se calcula solo -no todo el historial de patas está siempre al
día-, así que ambos campos se pueden corregir a mano en cualquier momento con
el botón "✏️" de cada tarjeta, sin que estén editándose todo el rato en
pantalla.
"""

from datetime import date

import streamlit as st

import database as db

NUEVA_CASA = "+ Añadir nueva casa…"
TIPOS_MOVIMIENTO = ["Depósito", "Retirada"]
TIPO_A_ETIQUETA = {"deposito": "Depósito", "retirada": "Retirada"}

# Dominio de cada casa conocida, para pedirle el favicon a Google como logo.
# Si una casa no está aquí (p.ej. una añadida a mano con otro nombre), se
# muestra un círculo de color con su inicial en vez de un logo real.
CASA_DOMINIOS = {
    "888sport": "888sport.es",
    "bet365": "bet365.es",
    "bet777": "bet777.es",
    "betfair": "betfair.es",
    "betway": "betway.es",
    "bwin": "bwin.es",
    "codere": "codere.es",
    "leovegas": "leovegas.es",
    "marathonbet": "marathonbet.es",
    "marcaapuestas": "marcaapuestas.es",
    "pokerstars": "pokerstars.es",
    "winamax": "winamax.es",
}

COLORES_INICIAL = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c", "#0891b2", "#ca8a04", "#db2777"]


def _logo_html(nombre):
    dominio = CASA_DOMINIOS.get(nombre.strip().lower())
    if dominio:
        return (
            f'<img src="https://www.google.com/s2/favicons?sz=64&domain={dominio}" '
            f'style="width:26px;height:26px;border-radius:6px;vertical-align:middle;'
            f'margin-right:8px;" />'
        )
    inicial = (nombre.strip()[:1] or "?").upper()
    color = COLORES_INICIAL[hash(nombre) % len(COLORES_INICIAL)]
    return (
        f'<span style="display:inline-flex;align-items:center;justify-content:center;'
        f'width:26px;height:26px;border-radius:6px;background:{color};color:white;'
        f'font-weight:700;font-size:0.8rem;vertical-align:middle;margin-right:8px;">'
        f"{inicial}</span>"
    )


def _mostrar_totales(casas):
    total_liquido = sum(c["liquido"] for c in casas)
    total_pendiente = sum(c["pendiente"] for c in casas)
    c1, c2, c3 = st.columns(3)
    c1.metric("Líquido total", f"{total_liquido:,.2f} €")
    c2.metric("En juego (total)", f"{total_pendiente:,.2f} €")
    c3.metric("Saldo total", f"{total_liquido + total_pendiente:,.2f} €")


def _formulario_movimiento(nombres_casas):
    st.subheader("Registrar depósito / retirada")
    with st.form("form_movimiento_bankroll", clear_on_submit=True):
        c1, c2, c3, c4, c5 = st.columns([2, 1.3, 1.3, 1.5, 1.1])
        casa = c1.selectbox("Casa", options=nombres_casas, key="mov_casa")
        tipo_ui = c2.selectbox("Tipo", options=TIPOS_MOVIMIENTO, key="mov_tipo")
        importe = c3.number_input("Importe (€)", min_value=0.01, step=1.0, value=50.0, key="mov_importe")
        fecha = c4.date_input("Fecha", value=date.today(), key="mov_fecha")
        c5.markdown("<div style='height:1.85rem'></div>", unsafe_allow_html=True)
        enviado = c5.form_submit_button("Registrar", use_container_width=True)
        if enviado:
            tipo_db = "deposito" if tipo_ui == "Depósito" else "retirada"
            db.registrar_movimiento_bankroll(casa, tipo_db, importe, fecha.isoformat())
            st.success(f"{tipo_ui} de {importe:,.2f} € registrado en {casa}.")
            st.rerun()


def _tarjeta_casa(casa, totales_movimientos):
    nombre = casa["casa_apuestas"]
    dep, ret = totales_movimientos.get(nombre, (0.0, 0.0))
    clave_editando = f"bankroll_editando_{nombre}"
    editando = st.session_state.get(clave_editando, False)

    with st.container(border=True):
        col_titulo, col_boton = st.columns([5, 1])
        with col_titulo:
            st.markdown(f"{_logo_html(nombre)}**{nombre}**", unsafe_allow_html=True)
        with col_boton:
            if st.button("✏️", key=f"btn_editar_{nombre}", help="Ajustar líquido / en juego"):
                st.session_state[clave_editando] = not editando
                st.rerun()

        if editando:
            with st.form(f"form_editar_{nombre}"):
                c1, c2 = st.columns(2)
                liquido = c1.number_input(
                    "Líquido (€)", value=float(casa["liquido"]), step=1.0,
                    key=f"liq_{nombre}_{casa['liquido']:.2f}",
                )
                pendiente = c2.number_input(
                    "En juego (€)", value=float(casa["pendiente"]), step=1.0,
                    key=f"pen_{nombre}_{casa['pendiente']:.2f}",
                )
                col_g, col_c = st.columns(2)
                guardar = col_g.form_submit_button("Guardar", use_container_width=True)
                cancelar = col_c.form_submit_button("Cancelar", use_container_width=True)
                if guardar:
                    db.guardar_bankroll(nombre, liquido, pendiente)
                    st.session_state[clave_editando] = False
                    st.rerun()
                if cancelar:
                    st.session_state[clave_editando] = False
                    st.rerun()
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("Líquido", f"{casa['liquido']:,.2f} €")
            m2.metric("En juego", f"{casa['pendiente']:,.2f} €")
            m3.metric("Saldo total", f"{casa['liquido'] + casa['pendiente']:,.2f} €")
            st.caption(f"Depositado: {dep:,.2f} € · Retirado: {ret:,.2f} €")


def _historial_movimientos(movimientos, nombres_casas):
    if not movimientos:
        return
    with st.expander(f"Ver historial completo de movimientos ({len(movimientos)})"):
        filtro = st.selectbox("Filtrar por casa", options=["Todas"] + nombres_casas, key="filtro_historial_mov")
        filtrados = movimientos if filtro == "Todas" else [m for m in movimientos if m["casa_apuestas"] == filtro]
        for m in filtrados:
            col_txt, col_del = st.columns([6, 1])
            with col_txt:
                signo = "+" if m["tipo"] == "deposito" else "-"
                hist_txt = " · histórico (no afectó al líquido)" if m["es_historico"] else ""
                nota_txt = f" · {m['nota']}" if m["nota"] else ""
                st.write(
                    f"{m['fecha']} · {m['casa_apuestas']} · {TIPO_A_ETIQUETA.get(m['tipo'], m['tipo'])} · "
                    f"{signo}{m['importe']:,.2f} €{hist_txt}{nota_txt}"
                )
            with col_del:
                if st.button("🗑️", key=f"del_mov_{m['id']}"):
                    db.eliminar_movimiento_bankroll(m["id"])
                    st.rerun()


def _formulario_nueva_casa(nombres_existentes):
    with st.expander("Añadir casa de apuestas"):
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
                    st.error("Ya existe una casa con ese nombre; edítala con el botón ✏️.")
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

    casas = db.listar_bankroll()
    movimientos = db.listar_movimientos_bankroll()
    nombres_existentes = [c["casa_apuestas"] for c in casas]

    if not casas:
        st.info("Todavía no hay ninguna casa. Añade la primera abajo.")
    else:
        _mostrar_totales(casas)

    st.markdown("---")
    if nombres_existentes:
        _formulario_movimiento(nombres_existentes)
        st.markdown("---")

    if casas:
        totales_movimientos = {}
        for m in movimientos:
            dep, ret = totales_movimientos.get(m["casa_apuestas"], (0.0, 0.0))
            if m["tipo"] == "deposito":
                dep += m["importe"]
            else:
                ret += m["importe"]
            totales_movimientos[m["casa_apuestas"]] = (dep, ret)

        columnas = st.columns(2)
        for i, casa in enumerate(casas):
            with columnas[i % 2]:
                _tarjeta_casa(casa, totales_movimientos)

        st.markdown("---")
        _historial_movimientos(movimientos, nombres_existentes)

    st.markdown("---")
    _formulario_nueva_casa(nombres_existentes)
    if nombres_existentes:
        _eliminar_casa(nombres_existentes)
