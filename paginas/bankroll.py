# paginas/bankroll.py
"""Pestaña de bankroll: líquido y dinero en juego por casa de apuestas.

El líquido y el importe en juego de cada casa se mueven solos:
- depósito / retirada: sube / baja el líquido.
- registrar una apuesta: el importe de cada pata pasa del líquido a en juego.
- resolverla: el importe sale de en juego y entra en el líquido lo que
  devuelve la casa (ganada: importe x cuota; anulada: el importe; cerrada: el
  importe de cierre; perdida: nada).
- eliminar una pendiente o reabrir una resuelta deshace lo anterior.

Las casas que ya no se usan se marcan como inactivas en vez de borrarse: no
salen para elegirlas, pero sus apuestas y movimientos se conservan.

Aun así, ambos campos se pueden cuadrar a mano con lo que marque la casa de
verdad con el botón "✏️" de cada tarjeta. Cada tarjeta avisa si 'en juego' no
coincide con lo apostado en las surebets pendientes de esa casa.
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


def _tarjeta_casa(casa, totales_movimientos, pendientes_por_casa):
    nombre = casa["casa_apuestas"]
    dep, ret = totales_movimientos.get(nombre, (0.0, 0.0))
    en_pendientes = pendientes_por_casa.get(nombre, 0.0)
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
                st.caption(f"Apostado en surebets pendientes de esta casa: {en_pendientes:,.2f} €")
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
            st.caption(
                f"Depositado: {dep:,.2f} € · Retirado: {ret:,.2f} € · "
                f"En surebets pendientes: {en_pendientes:,.2f} €"
            )
            if abs(casa["pendiente"] - en_pendientes) > 0.005:
                st.warning(
                    f"'En juego' ({casa['pendiente']:,.2f} €) no cuadra con lo apostado en las surebets "
                    f"pendientes ({en_pendientes:,.2f} €). Corrígelo con ✏️ si la casa marca otra cosa."
                )


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


def _formulario_nueva_casa(nombres_existentes, nombres_inactivas):
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
                elif nombre in nombres_inactivas:
                    st.error(f"'{nombre}' ya existe pero está inactiva; reactívala en 'Desactivadas'.")
                elif nombre in nombres_existentes:
                    st.error("Ya existe una casa con ese nombre; edítala con el botón ✏️.")
                else:
                    db.guardar_bankroll(nombre, liquido_ini, pendiente_ini)
                    st.success(f"'{nombre}' añadida.")
                    st.rerun()


def _desactivar_casa(casas_por_nombre, pendientes_por_casa):
    """Marca como inactiva una casa que ya no se usa: deja de salir para
    elegirla, pero sus apuestas y movimientos siguen en Historial y
    Dashboard. Se ofrecen todas las casas activas, también las que solo
    aparecen en apuestas antiguas (p.ej. una que se borró del bankroll)."""
    nombres = db.listar_nombres_casas()
    if not nombres:
        return
    with st.expander("Desactivar una casa"):
        st.caption(
            "Una casa inactiva no sale para elegirla al registrar apuestas ni movimientos, pero sus "
            "apuestas, depósitos y retiradas se conservan en Historial y Dashboard. Puedes reactivarla "
            "cuando quieras desde su tarjeta, en 'Desactivadas'."
        )
        nombre = st.selectbox("Casa", options=nombres, key="bankroll_casa_a_desactivar")
        casa = casas_por_nombre.get(nombre)
        saldo = (casa["liquido"] + casa["pendiente"]) if casa else 0.0
        en_pendientes = pendientes_por_casa.get(nombre, 0.0)
        avisos = []
        if abs(saldo) > 0.005:
            avisos.append(f"todavía tiene un saldo de {saldo:,.2f} €")
        if en_pendientes > 0.005:
            avisos.append(f"tiene {en_pendientes:,.2f} € en surebets pendientes")
        confirmado = True
        if avisos:
            st.warning(f"{nombre} {' y '.join(avisos)}.")
            confirmado = st.checkbox("Desactivarla igualmente", key=f"bankroll_confirmar_desactivar_{nombre}")
        if st.button("🚫 Desactivar", key="bankroll_btn_desactivar", disabled=not confirmado):
            db.desactivar_casa(nombre)
            st.rerun()


def _tarjetas_inactivas(inactivas):
    """Parrilla aparte, siempre debajo de las activas, con las casas
    desactivadas en gris: solo se ven sus importes y se pueden reactivar."""
    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    st.markdown(f"#### 🚫 Desactivadas ({len(inactivas)})")
    st.caption("No salen para elegirlas al registrar apuestas ni movimientos; su historial se conserva.")
    columnas = st.columns(2)
    for i, casa in enumerate(inactivas):
        nombre = casa["casa_apuestas"]
        with columnas[i % 2]:
            with st.container(border=True):
                col_titulo, col_boton = st.columns([3, 1.4], vertical_alignment="center")
                col_titulo.markdown(
                    f"<div style='opacity:0.5;filter:grayscale(1);'>{_logo_html(nombre)}<b>{nombre}</b>"
                    f" <span style='font-size:0.8rem;'>· desactivada</span></div>",
                    unsafe_allow_html=True,
                )
                if col_boton.button("↩️ Reactivar", key=f"bankroll_reactivar_{nombre}", use_container_width=True):
                    db.reactivar_casa(nombre)
                    st.rerun()
                st.markdown(
                    f"<div style='opacity:0.5;font-size:0.9rem;'>Líquido {casa['liquido']:,.2f} € · "
                    f"En juego {casa['pendiente']:,.2f} € · "
                    f"Saldo {casa['liquido'] + casa['pendiente']:,.2f} €</div>",
                    unsafe_allow_html=True,
                )


def render():
    st.subheader("Bankroll por casa de apuestas")

    casas = db.listar_bankroll()
    movimientos = db.listar_movimientos_bankroll()
    pendientes_por_casa = db.importes_pendientes_por_casa()
    # Los totales cuentan también las inactivas, para que no desaparezca
    # dinero que pudiera quedar en ellas; tarjetas y desplegables, solo las activas.
    activas = [c for c in casas if c["activa"]]
    inactivas = [c for c in casas if not c["activa"]]
    nombres_activas = [c["casa_apuestas"] for c in activas]
    nombres_existentes = [c["casa_apuestas"] for c in casas]

    if not activas:
        st.info("Todavía no hay ninguna casa activa. Añade la primera abajo.")
    if casas:
        _mostrar_totales(casas)

    st.markdown("---")
    if nombres_activas:
        _formulario_movimiento(nombres_activas)
        st.markdown("---")

    if activas:
        totales_movimientos = {}
        for m in movimientos:
            dep, ret = totales_movimientos.get(m["casa_apuestas"], (0.0, 0.0))
            if m["tipo"] == "deposito":
                dep += m["importe"]
            else:
                ret += m["importe"]
            totales_movimientos[m["casa_apuestas"]] = (dep, ret)

        columnas = st.columns(2)
        for i, casa in enumerate(activas):
            with columnas[i % 2]:
                _tarjeta_casa(casa, totales_movimientos, pendientes_por_casa)

    if inactivas:
        _tarjetas_inactivas(inactivas)

    if activas or inactivas:
        st.markdown("---")
    nombres_movimientos = sorted(set(nombres_existentes) | {m["casa_apuestas"] for m in movimientos})
    _historial_movimientos(movimientos, nombres_movimientos)

    st.markdown("---")
    _formulario_nueva_casa(nombres_existentes, [c["casa_apuestas"] for c in inactivas])
    _desactivar_casa({c["casa_apuestas"]: c for c in casas}, pendientes_por_casa)
