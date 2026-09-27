# paginas/bankroll.py
"""Pestaña de bankroll: saldo, dinero en juego y líquido disponible por casa de
apuestas.

El saldo de cada casa no se guarda como un número que haya que ir corrigiendo
a mano: se calcula cada vez a partir de dos cosas que ya tenemos (o que se
registran aquí una sola vez):
  - los movimientos manuales (depósitos, retiradas o ajustes) que introduzcas, y
  - el resultado de las patas ya resueltas de cada surebet (ganada, perdida,
    anulada o cerrada).
Así, en cuanto resuelves una apuesta en 'Registrar apuesta', el bankroll de esa
casa se actualiza solo, sin ningún paso adicional.
"""

from datetime import date

import pandas as pd
import streamlit as st

import database as db

TIPOS_MOVIMIENTO = ["Depósito", "Retirada", "Ajuste"]
NUEVA_CASA = "+ Añadir nueva casa…"


def _cargar_datos():
    _, patas = db.obtener_todo_dataframe()
    movimientos = pd.DataFrame(db.listar_movimientos_casa())
    if movimientos.empty:
        movimientos = pd.DataFrame(columns=["id", "casa_apuestas", "tipo", "importe", "fecha", "nota", "creado_en"])
    return patas, movimientos


def _neto_pata(fila):
    """Cambio en el saldo de la casa al resolverse esta pata (retorno recibido
    menos lo que ya estaba apostado). 0 si sigue pendiente o fue anulada."""
    if fila["resultado"] == "ganada":
        return fila["importe"] * (fila["cuota"] - 1)
    if fila["resultado"] == "perdida":
        return -fila["importe"]
    if fila["resultado"] == "cerrada":
        return (fila["importe_cierre"] or 0.0) - fila["importe"]
    return 0.0  # pendiente o anulada: no cambia el saldo total


def _resumen_por_casa(patas: pd.DataFrame, movimientos: pd.DataFrame) -> pd.DataFrame:
    casas = set()
    if not patas.empty:
        casas |= set(patas["casa_apuestas"].unique())
    if not movimientos.empty:
        casas |= set(movimientos["casa_apuestas"].unique())

    filas = []
    for casa in sorted(casas):
        patas_casa = patas[patas["casa_apuestas"] == casa] if not patas.empty else pd.DataFrame()
        movs_casa = movimientos[movimientos["casa_apuestas"] == casa] if not movimientos.empty else pd.DataFrame()

        aportado_neto = movs_casa["importe"].sum() if not movs_casa.empty else 0.0
        if not patas_casa.empty:
            beneficio_neto = patas_casa.apply(_neto_pata, axis=1).sum()
            pendiente = patas_casa[patas_casa["resultado"] == "pendiente"]["importe"].sum()
        else:
            beneficio_neto = 0.0
            pendiente = 0.0

        saldo_total = aportado_neto + beneficio_neto
        liquido = saldo_total - pendiente

        filas.append(
            {
                "Casa": casa,
                "Saldo total": saldo_total,
                "Pendiente": pendiente,
                "Líquido": liquido,
            }
        )

    return pd.DataFrame(filas, columns=["Casa", "Saldo total", "Pendiente", "Líquido"])


def _mostrar_resumen(resumen: pd.DataFrame):
    total_saldo = resumen["Saldo total"].sum()
    total_pendiente = resumen["Pendiente"].sum()
    total_liquido = resumen["Líquido"].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Saldo total", f"{total_saldo:,.2f} €")
    c2.metric("En juego (pendiente)", f"{total_pendiente:,.2f} €")
    c3.metric("Líquido disponible", f"{total_liquido:,.2f} €")

    st.markdown("---")

    columnas = st.columns(3)
    for i, fila in resumen.iterrows():
        with columnas[i % 3]:
            with st.container(border=True):
                st.markdown(f"**{fila['Casa']}**")
                st.metric("Líquido", f"{fila['Líquido']:,.2f} €")
                st.caption(
                    f"En juego: {fila['Pendiente']:,.2f} € · Saldo total: {fila['Saldo total']:,.2f} €"
                )


def _formulario_movimiento(casas_existentes):
    st.subheader("Registrar depósito / retirada / ajuste")
    st.caption(
        "Usa esto para fijar cuánto dinero tienes puesto en cada casa (depósitos y retiradas). "
        "El efecto de ganar o perder una apuesta ya se calcula solo a partir del historial."
    )

    with st.form("form_movimiento_casa", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            opciones_casa = list(casas_existentes) + [NUEVA_CASA]
            casa_sel = st.selectbox("Casa de apuestas", options=opciones_casa)
            casa_nueva = ""
            if casa_sel == NUEVA_CASA:
                casa_nueva = st.text_input("Nombre de la nueva casa")
            tipo = st.selectbox("Tipo de movimiento", options=TIPOS_MOVIMIENTO)
        with col2:
            importe = st.number_input("Importe (€)", min_value=0.01, step=10.0, value=50.0)
            fecha = st.date_input("Fecha", value=date.today())
        nota = st.text_input("Nota (opcional)")

        enviado = st.form_submit_button("Guardar movimiento")
        if enviado:
            casa_final = casa_nueva.strip() if casa_sel == NUEVA_CASA else casa_sel
            if not casa_final:
                st.error("Indica el nombre de la casa de apuestas.")
            else:
                signo = -1 if tipo == "Retirada" else 1
                db.crear_movimiento_casa(casa_final, tipo.lower(), signo * importe, fecha.isoformat(), nota or None)
                st.success(f"Movimiento guardado en {casa_final}.")
                st.rerun()


def _historial_movimientos(movimientos: pd.DataFrame):
    if movimientos.empty:
        return
    with st.expander("Ver historial de depósitos / retiradas / ajustes"):
        for _, mov in movimientos.iterrows():
            col_txt, col_del = st.columns([6, 1])
            with col_txt:
                signo = "+" if mov["importe"] >= 0 else ""
                nota_txt = f" · {mov['nota']}" if mov["nota"] else ""
                st.write(
                    f"**{mov['fecha']}** · {mov['casa_apuestas']} · {mov['tipo'].capitalize()} · "
                    f"{signo}{mov['importe']:,.2f} €{nota_txt}"
                )
            with col_del:
                if st.button("🗑️", key=f"del_mov_{mov['id']}"):
                    db.eliminar_movimiento_casa(mov["id"])
                    st.rerun()


def render():
    st.subheader("Bankroll por casa de apuestas")

    patas, movimientos = _cargar_datos()
    resumen = _resumen_por_casa(patas, movimientos)

    if resumen.empty:
        st.info(
            "Todavía no hay ninguna casa de apuestas. Registra un depósito abajo para empezar "
            "a llevar el bankroll, o registra una apuesta desde 'Registrar apuesta'."
        )
    else:
        _mostrar_resumen(resumen)

    st.markdown("---")
    _formulario_movimiento(sorted(resumen["Casa"]) if not resumen.empty else [])
    _historial_movimientos(movimientos)
