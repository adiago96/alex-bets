# paginas/oportunidades.py
"""Pestaña de oportunidades detectadas automáticamente en el canal de Telegram."""

from datetime import datetime

import streamlit as st

import database as db
from calculos import calcular_beneficios_por_seleccion, calcular_sugerencia_agrupada

IMPORTE_POR_DEFECTO = 100.0


def _tiempo_restante(oportunidad):
    """Tiempo hasta el inicio recalculado en el momento de mostrarlo (el texto
    original del canal, ej. '5h 37m', se queda desactualizado en cuanto pasa
    el tiempo). Si no se pudo calcular la hora exacta, usa el texto original."""
    if not oportunidad["empieza_en"]:
        return oportunidad["comienza_en"]
    restante = datetime.fromisoformat(oportunidad["empieza_en"]) - datetime.now()
    if restante.total_seconds() <= 0:
        return "ya ha empezado"
    horas, resto = divmod(int(restante.total_seconds()), 3600)
    minutos = resto // 60
    return f"{horas}h {minutos}m"


def _calcular_reparto_y_beneficio(selecciones, cuotas, importe_total):
    """Importe sugerido por pata y beneficio garantizado (el peor de los
    casos) para un importe total dado. Devuelve (importes, beneficio); ambos
    None si las cuotas no forman una surebet válida."""
    try:
        importes = calcular_sugerencia_agrupada(selecciones, cuotas, importe_total)
    except ValueError:
        return None, None
    beneficios = calcular_beneficios_por_seleccion(selecciones, cuotas, importes)
    return importes, min(beneficios)


def _mostrar_oportunidad(oportunidad, patas, importe_base):
    selecciones = [p["seleccion"] for p in patas]
    cuotas = [p["cuota"] for p in patas]

    importe_key = f"importe_oportunidad_{oportunidad['id']}"
    importe_actual = st.session_state.get(importe_key, importe_base)
    _, beneficio_cabecera = _calcular_reparto_y_beneficio(selecciones, cuotas, importe_actual)
    beneficio_txt = f"{beneficio_cabecera:.2f} €" if beneficio_cabecera is not None else "?"

    with st.expander(
        f"💰 {beneficio_txt} · 📈 ROI {oportunidad['roi_pct']:.2f}% · {oportunidad['evento']} · "
        f"{oportunidad['torneo']} · empieza en {_tiempo_restante(oportunidad)}"
    ):
        importe_total = st.number_input(
            "Importe total a repartir (€)",
            min_value=1.0,
            value=importe_base,
            step=1.0,
            key=importe_key,
        )
        importes_sugeridos, beneficio = _calcular_reparto_y_beneficio(selecciones, cuotas, importe_total)
        if beneficio is None:
            st.warning("No se puede calcular la sugerencia con estas cuotas.")
            importes_sugeridos = [None] * len(patas)

        for pata, sugerido in zip(patas, importes_sugeridos):
            col1, col2, col3, col4 = st.columns([2, 3, 1, 1.5])
            col1.write(pata["casa_apuestas"])
            col2.write(pata["seleccion"])
            col3.write(f"Cuota {pata['cuota']:.2f}")
            col4.write(f"💡 {sugerido:.2f} €" if sugerido is not None else "—")

        if beneficio is not None:
            st.success(
                f"Beneficio garantizado: **{beneficio:.2f} €** ({beneficio / importe_total * 100:.2f}%) "
                f"invirtiendo {importe_total:.2f} €"
            )

        col_a, col_b = st.columns([1, 1])
        with col_a:
            if st.button("✅ Usar en Registrar apuesta", key=f"usar_{oportunidad['id']}"):
                st.session_state.patas_temp = [
                    {"casa_apuestas": p["casa_apuestas"], "seleccion": p["seleccion"], "cuota": p["cuota"]}
                    for p in patas
                ]
                db.marcar_oportunidad_usada(oportunidad["id"])
                st.success("Cargada. Ve a la pestaña 'Registrar apuesta' para completarla.")
                st.rerun()
        with col_b:
            if st.button("🗑️ Descartar", key=f"descartar_{oportunidad['id']}"):
                db.eliminar_oportunidad(oportunidad["id"])
                st.rerun()


def render():
    st.subheader("Oportunidades detectadas en Telegram")
    st.caption(
        "Esta lista se rellena sola cuando el listener de Telegram detecta un mensaje "
        "nuevo en el canal. Ejecuta `python telegram_listener.py` en una terminal aparte "
        "para que se mantenga actualizada."
    )

    importe_base = st.number_input(
        "Importe habitual a invertir por oportunidad (€)",
        min_value=1.0,
        value=IMPORTE_POR_DEFECTO,
        step=1.0,
        key="importe_base_oportunidades",
    )

    if st.session_state.get("_importe_base_anterior") != importe_base:
        # El importe habitual ha cambiado: se reinician los importes por
        # oportunidad para que reflejen el nuevo valor (si no, cada
        # desplegable se quedaría con el importe que tenía la primera vez
        # que se abrió, aunque cambiaras el importe habitual después).
        for key in list(st.session_state.keys()):
            if key.startswith("importe_oportunidad_"):
                del st.session_state[key]
        st.session_state["_importe_base_anterior"] = importe_base

    if st.button("🔄 Actualizar"):
        st.rerun()

    db.eliminar_oportunidades_caducadas()
    oportunidades = db.listar_oportunidades()
    if not oportunidades:
        st.info("No hay oportunidades pendientes de revisar todavía.")
        return

    con_patas = [(op, db.listar_oportunidad_patas(op["id"])) for op in oportunidades]

    def _beneficio_para_orden(item):
        oportunidad, patas = item
        importe_actual = st.session_state.get(f"importe_oportunidad_{oportunidad['id']}", importe_base)
        _, beneficio = _calcular_reparto_y_beneficio(
            [p["seleccion"] for p in patas], [p["cuota"] for p in patas], importe_actual
        )
        return beneficio if beneficio is not None else float("-inf")

    con_patas.sort(key=_beneficio_para_orden, reverse=True)

    for oportunidad, patas in con_patas:
        _mostrar_oportunidad(oportunidad, patas, importe_base)
