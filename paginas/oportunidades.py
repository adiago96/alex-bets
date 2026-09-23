# paginas/oportunidades.py
"""Pestaña de oportunidades detectadas automáticamente en el canal de Telegram."""

import html
from datetime import datetime

import streamlit as st

import database as db
import telegram_sync
from calculos import calcular_beneficios_por_seleccion, calcular_sugerencia_agrupada

IMPORTE_POR_DEFECTO = 100.0

# URL de cada casa de apuestas (siempre la misma, no depende del evento).
CASA_URLS = {
    "bet365": "https://www.bet365.es",
    "bwin": "https://www.bwin.es",
    "betfair": "https://www.betfair.es",
    "william hill": "https://www.williamhill.es",
    "codere": "https://www.codere.es",
    "marathonbet": "https://www.marathonbet.es",
    "pinnacle": "https://www.pinnacle.com",
    "betsson": "https://www.betsson.es",
    "winamax": "https://www.winamax.es",
    "luckia": "https://www.luckia.es",
    "leovegas": "https://www.leovegas.es",
}


def _enlace_casa(casa_apuestas):
    texto = html.escape(casa_apuestas)
    url = CASA_URLS.get(casa_apuestas.strip().lower())
    if not url:
        return texto
    return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{texto}</a>'


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


def _fecha_hora_evento(oportunidad):
    """Fecha y hora exactas del evento (hora de inicio del mensaje de Telegram
    más la duración indicada en 'Comienza en: ...'), o None si no se pudo
    calcular."""
    if not oportunidad["empieza_en"]:
        return None
    return datetime.fromisoformat(oportunidad["empieza_en"])


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

    fecha_hora = _fecha_hora_evento(oportunidad)
    fecha_hora_txt = fecha_hora.strftime("%d/%m %H:%M") if fecha_hora else "?"

    with st.expander(
        f"💰 {beneficio_txt} · 📈 ROI {oportunidad['roi_pct']:.2f}% · {oportunidad['evento']} · "
        f"{oportunidad['torneo']} · 📅 {fecha_hora_txt} (en {_tiempo_restante(oportunidad)})"
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
            with st.container(border=True):
                st.markdown(
                    f"{_enlace_casa(pata['casa_apuestas'])} — {pata['seleccion']}", unsafe_allow_html=True
                )
                sugerido_txt = f"💡 Sugerido: {sugerido:.2f} €" if sugerido is not None else "—"
                st.caption(f"Cuota {pata['cuota']:.2f} · {sugerido_txt}")

        if beneficio is not None:
            st.success(
                f"Beneficio garantizado: **{beneficio:.2f} €** ({beneficio / importe_total * 100:.2f}%) "
                f"invirtiendo {importe_total:.2f} €"
            )

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button(
                "✅ Usar en Registrar apuesta", key=f"usar_{oportunidad['id']}", use_container_width=True
            ):
                st.session_state.patas_temp = [
                    {"casa_apuestas": p["casa_apuestas"], "seleccion": p["seleccion"], "cuota": p["cuota"]}
                    for p in patas
                ]
                db.marcar_oportunidad_usada(oportunidad["id"])
                st.success("Cargada. Ve a la pestaña 'Registrar apuesta' para completarla.")
                st.rerun()
        with col_b:
            if st.button("🗑️ Descartar", key=f"descartar_{oportunidad['id']}", use_container_width=True):
                db.eliminar_oportunidad(oportunidad["id"])
                st.rerun()


def _sincronizar_con_telegram(forzar=False):
    try:
        guardadas = telegram_sync.sincronizar(forzar=forzar)
    except Exception as e:
        st.warning(f"No se pudo sincronizar con Telegram: {e}")
        return
    if guardadas:
        st.toast(f"🔭 {guardadas} oportunidad(es) nueva(s) o actualizada(s) desde Telegram.")


def render():
    st.subheader("Oportunidades detectadas en Telegram")
    st.caption(
        "Se sincroniza sola con el canal de Telegram solo la primera vez que entras "
        "en la sesión. Pulsa 'Actualizar ahora' para traer las nuevas en cualquier momento."
    )

    if not st.session_state.get("_sync_telegram_hecho"):
        st.session_state["_sync_telegram_hecho"] = True
        _sincronizar_con_telegram()

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

    if st.button("🔄 Actualizar ahora"):
        with st.spinner("Consultando el canal de Telegram..."):
            _sincronizar_con_telegram(forzar=True)
        st.rerun()

    db.eliminar_oportunidades_caducadas()
    oportunidades = db.listar_oportunidades()
    if not oportunidades:
        st.info("No hay oportunidades pendientes de revisar todavía.")
        return

    con_patas = [(op, db.listar_oportunidad_patas(op["id"])) for op in oportunidades]

    orden = st.radio(
        "Ordenar por",
        options=["Fecha y hora del evento", "Beneficio"],
        horizontal=True,
        key="orden_oportunidades",
    )

    if orden == "Fecha y hora del evento":
        def _clave_orden(item):
            oportunidad, _ = item
            fecha_hora = _fecha_hora_evento(oportunidad)
            return fecha_hora if fecha_hora else datetime.max

        con_patas.sort(key=_clave_orden)
    else:
        def _clave_orden(item):
            oportunidad, patas = item
            importe_actual = st.session_state.get(f"importe_oportunidad_{oportunidad['id']}", importe_base)
            _, beneficio = _calcular_reparto_y_beneficio(
                [p["seleccion"] for p in patas], [p["cuota"] for p in patas], importe_actual
            )
            return beneficio if beneficio is not None else float("-inf")

        con_patas.sort(key=_clave_orden, reverse=True)

    for oportunidad, patas in con_patas:
        _mostrar_oportunidad(oportunidad, patas, importe_base)
