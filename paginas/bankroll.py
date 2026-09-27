# paginas/bankroll.py
"""Pestaña de bankroll: líquido y dinero en juego por casa de apuestas.

A diferencia del resto de la app, el líquido y el importe en juego de cada
casa no se calculan a partir del historial de apuestas: son cifras que tú
escribes y guardas directamente, porque solo tú sabes lo que de verdad tienes
en cada casa en cada momento. Así puedes corregir cualquier desajuste sin
tener que "engañar" al sistema con depósitos o retiradas ficticias.

Aparte, cada casa lleva un historial de depósitos y retiradas. Los que se
marcan como histórico (importados de antes de llevar el bankroll aquí) son
solo para consulta y no tocan el líquido. Los que registras desde ahora en
adelante sí lo actualizan automáticamente: un depósito lo sube, una retirada
lo baja.
"""

from datetime import date

import streamlit as st

import database as db

NUEVA_CASA = "+ Añadir nueva casa…"
TIPOS_MOVIMIENTO = ["Depósito", "Retirada"]
TIPO_A_ETIQUETA = {"deposito": "Depósito", "retirada": "Retirada"}


def _mostrar_totales(casas):
    total_liquido = sum(c["liquido"] for c in casas)
    total_pendiente = sum(c["pendiente"] for c in casas)
    c1, c2, c3 = st.columns(3)
    c1.metric("Líquido total", f"{total_liquido:,.2f} €")
    c2.metric("En juego (total)", f"{total_pendiente:,.2f} €")
    c3.metric("Saldo total", f"{total_liquido + total_pendiente:,.2f} €")


def _historial_y_formulario_movimientos(nombre, movimientos_casa):
    with st.expander("💶 Depósitos / retiradas"):
        if movimientos_casa:
            total_dep = sum(m["importe"] for m in movimientos_casa if m["tipo"] == "deposito")
            total_ret = sum(m["importe"] for m in movimientos_casa if m["tipo"] == "retirada")
            st.caption(f"Total depositado: {total_dep:,.2f} € · Total retirado: {total_ret:,.2f} €")
            for m in movimientos_casa:
                col_txt, col_del = st.columns([5, 1])
                with col_txt:
                    signo = "+" if m["tipo"] == "deposito" else "-"
                    hist_txt = " · histórico (no afectó al líquido)" if m["es_historico"] else ""
                    nota_txt = f" · {m['nota']}" if m["nota"] else ""
                    st.write(
                        f"{m['fecha']} · {TIPO_A_ETIQUETA.get(m['tipo'], m['tipo'])} · "
                        f"{signo}{m['importe']:,.2f} €{hist_txt}{nota_txt}"
                    )
                with col_del:
                    if st.button("🗑️", key=f"del_mov_{m['id']}"):
                        db.eliminar_movimiento_bankroll(m["id"])
                        st.rerun()
            st.markdown("---")
        else:
            st.caption("Todavía no hay movimientos registrados en esta casa.")

        st.markdown("**Registrar nuevo movimiento**")
        with st.form(f"form_mov_{nombre}", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            tipo_ui = col_a.selectbox("Tipo", options=TIPOS_MOVIMIENTO, key=f"tipo_mov_{nombre}")
            importe_mov = col_b.number_input(
                "Importe (€)", min_value=0.01, step=1.0, value=50.0, key=f"importe_mov_{nombre}"
            )
            fecha_mov = st.date_input("Fecha", value=date.today(), key=f"fecha_mov_{nombre}")
            nota_mov = st.text_input("Nota (opcional)", key=f"nota_mov_{nombre}")
            if st.form_submit_button("Guardar movimiento"):
                tipo_db = "deposito" if tipo_ui == "Depósito" else "retirada"
                db.registrar_movimiento_bankroll(
                    nombre, tipo_db, importe_mov, fecha_mov.isoformat(), nota_mov or None
                )
                st.success(f"Movimiento guardado. Líquido de {nombre} actualizado.")
                st.rerun()


def _tarjeta_casa(casa, movimientos_casa):
    nombre = casa["casa_apuestas"]
    with st.container(border=True):
        st.markdown(f"**{nombre}**")
        with st.form(f"form_bankroll_{nombre}"):
            col_a, col_b = st.columns(2)
            # La clave incluye el valor actual guardado en BD: así, cuando un
            # depósito/retirada o una eliminación cambian el líquido "por
            # detrás", el campo se refresca solo en vez de quedarse con el
            # último valor que Streamlit recuerde para una clave fija.
            liquido = col_a.number_input(
                "Líquido (€)", value=float(casa["liquido"]), step=1.0,
                key=f"liq_{nombre}_{casa['liquido']:.2f}",
            )
            pendiente = col_b.number_input(
                "En juego (€)", value=float(casa["pendiente"]), step=1.0,
                key=f"pen_{nombre}_{casa['pendiente']:.2f}",
            )
            if st.form_submit_button("Guardar", use_container_width=True):
                db.guardar_bankroll(nombre, liquido, pendiente)
                st.rerun()
        st.caption(f"Saldo total: {casa['liquido'] + casa['pendiente']:,.2f} €")
        _historial_y_formulario_movimientos(nombre, movimientos_casa)


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
    movimientos = db.listar_movimientos_bankroll()

    if not casas:
        st.info("Todavía no hay ninguna casa. Añade la primera abajo.")
    else:
        _mostrar_totales(casas)
        st.markdown("---")
        columnas = st.columns(2)
        for i, casa in enumerate(casas):
            movimientos_casa = [m for m in movimientos if m["casa_apuestas"] == casa["casa_apuestas"]]
            with columnas[i % 2]:
                _tarjeta_casa(casa, movimientos_casa)

    st.markdown("---")
    nombres_existentes = [c["casa_apuestas"] for c in casas]
    _formulario_nueva_casa(nombres_existentes)
    if nombres_existentes:
        _eliminar_casa(nombres_existentes)
