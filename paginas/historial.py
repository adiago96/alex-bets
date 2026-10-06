# paginas/historial.py
"""Pestaña de historial: listado detallado de cada surebet y cómo quedó cada pata."""

import pandas as pd
import streamlit as st

import database as db
from calculos import resumen_por_casa
from informes import pdf_beneficio_por_casa


def _cargar_datos():
    return db.obtener_todo_dataframe()


TODOS = "Todos"


def _opciones(serie: pd.Series) -> list:
    return [TODOS] + sorted(v for v in serie.dropna().unique() if str(v).strip())


def _aplicar_filtros(surebets: pd.DataFrame, patas: pd.DataFrame):
    col1, col2, col3, col4 = st.columns(4)
    estado_sel = col1.selectbox(
        "Estado", options=[TODOS, "pendiente", "resuelta"], index=0, key="hist_estado_sel",
        format_func=lambda v: v.capitalize(),
    )
    deporte_sel = col2.selectbox("Deporte", options=_opciones(surebets["deporte"]), key="hist_deporte_sel")
    mercado_sel = col3.selectbox("Mercado", options=_opciones(surebets["mercado"]), key="hist_mercado_sel")
    casas = _opciones(patas["casa_apuestas"]) if not patas.empty else [TODOS]
    casa_sel = col4.selectbox("Casa de apuestas", options=casas, key="hist_casa_sel")

    if not surebets.empty:
        fecha_min = surebets["fecha_ref"].min().date()
        fecha_max = surebets["fecha_ref"].max().date()
        rango_fechas = st.date_input(
            "Rango de fechas (del evento)",
            value=(fecha_min, fecha_max),
            min_value=fecha_min,
            max_value=fecha_max,
            key="hist_fechas",
        )
    else:
        rango_fechas = None

    df = surebets.copy()
    if not df.empty:
        if estado_sel != TODOS:
            df = df[df["estado"] == estado_sel]
        if deporte_sel != TODOS:
            df = df[df["deporte"] == deporte_sel]
        if mercado_sel != TODOS:
            df = df[df["mercado"] == mercado_sel]
        if rango_fechas and len(rango_fechas) == 2:
            inicio, fin = rango_fechas
            df = df[(df["fecha_ref"].dt.date >= inicio) & (df["fecha_ref"].dt.date <= fin)]

    if casa_sel != TODOS:
        ids_por_casa = set(patas[patas["casa_apuestas"] == casa_sel]["surebet_id"])
        df = df[df["id"].isin(ids_por_casa)]

    patas_filtradas = patas[patas["surebet_id"].isin(df["id"])] if not patas.empty else patas
    if not (rango_fechas and len(rango_fechas) == 2):
        rango_fechas = (None, None)
    return df.sort_values("fecha_ref", ascending=False), patas_filtradas, casa_sel, rango_fechas


def _tabla_resumen(df: pd.DataFrame):
    resumen = pd.DataFrame(
        {
            "Fecha evento": df["fecha_ref"].dt.strftime("%Y-%m-%d"),
            "Fecha apuesta": df["fecha"].dt.strftime("%Y-%m-%d"),
            "Evento": df["evento"],
            "Deporte": df["deporte"],
            "Mercado": df["mercado"],
            "Estado": df["estado"],
            "Importe total (€)": df["importe_total"].round(2),
            "Beneficio esperado (€)": df["beneficio_esperado_importe"].round(2),
            "Beneficio real (€)": df["beneficio_real"].round(2),
            "ROI (%)": (df["beneficio_real"] / df["importe_total"] * 100).round(2),
        }
    )
    st.dataframe(resumen, use_container_width=True, hide_index=True)


def _detalle_por_surebet(df: pd.DataFrame, patas: pd.DataFrame):
    st.markdown("**Detalle por surebet**")
    for _, surebet in df.iterrows():
        patas_surebet = patas[patas["surebet_id"] == surebet["id"]]
        if surebet["estado"] == "resuelta":
            estado_icono = "✅" if surebet["beneficio_real"] >= 0 else "❌"
            beneficio_txt = f"beneficio real: {surebet['beneficio_real']:.2f} €"
        else:
            estado_icono = "⏳"
            beneficio_txt = f"beneficio esperado: {surebet['beneficio_esperado_importe']:.2f} €"

        with st.expander(
            f"{estado_icono} {surebet['fecha_ref'].strftime('%Y-%m-%d')} · {surebet['evento']} · "
            f"{surebet['deporte']} · {surebet['mercado']} · {beneficio_txt}"
        ):
            tabla_patas = patas_surebet[
                ["casa_apuestas", "seleccion", "cuota", "importe", "resultado", "importe_cierre"]
            ].rename(
                columns={
                    "casa_apuestas": "Casa de apuestas",
                    "seleccion": "Selección",
                    "cuota": "Cuota",
                    "importe": "Importe (€)",
                    "resultado": "Resultado",
                    "importe_cierre": "Importe de cierre (€)",
                }
            )
            st.dataframe(tabla_patas, use_container_width=True, hide_index=True)

            col1, col2, col3 = st.columns(3)
            col1.metric("Importe total", f"{surebet['importe_total']:.2f} €")
            col2.metric("Beneficio esperado", f"{surebet['beneficio_esperado_importe']:.2f} €")
            if surebet["estado"] == "resuelta":
                col3.metric("Beneficio real", f"{surebet['beneficio_real']:.2f} €")
            else:
                col3.metric("Estado", "Pendiente")

            if surebet["notas"]:
                st.caption(f"Notas: {surebet['notas']}")

            if surebet["estado"] == "resuelta":
                st.markdown("---")
                if st.button(
                    "↩️ Reabrir (volver a pendiente)",
                    key=f"reabrir_{surebet['id']}",
                    help="Pon el resultado de cada pata otra vez en pendiente para corregirlo desde "
                    "'Pendientes'. Deshace también lo que movió en el bankroll al resolverla.",
                ):
                    db.reabrir_surebet(surebet["id"])
                    st.success("Surebet reabierta. Ya puedes corregirla en 'Registrar apuesta'.")
                    st.rerun()


def _resumen_por_casa(df: pd.DataFrame, patas: pd.DataFrame, casa_sel: str, rango_fechas: tuple):
    """Totales por casa de apuestas y, debajo, todas las patas jugadas en cada una."""
    if casa_sel != TODOS:
        patas = patas[patas["casa_apuestas"] == casa_sel]
    if patas.empty:
        st.info("No hay apuestas para mostrar por casa de apuestas.")
        return
    patas_originales = patas
    resumen, patas = resumen_por_casa(df, patas)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Importe apostado", f"{resumen['apostado'].sum():,.2f} €")
    c2.metric("Importe devuelto", f"{resumen['devuelto'].sum():,.2f} €")
    c3.metric("Beneficio", f"{resumen['beneficio'].sum():+,.2f} €")
    c4.metric("En juego", f"{resumen['en_juego'].sum():,.2f} €")

    st.dataframe(
        pd.DataFrame(
            {
                "Casa de apuestas": resumen["casa_apuestas"],
                "Nº apuestas": resumen["apuestas"],
                "Importe apostado (€)": resumen["apostado"].round(2),
                "Importe devuelto (€)": resumen["devuelto"].round(2),
                "Beneficio (€)": resumen["beneficio"].round(2),
                "ROI (%)": resumen["roi"].round(2),
                "En juego (€)": resumen["en_juego"].round(2),
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "Apostado, devuelto y beneficio cuentan las surebets ya resueltas: devuelto es lo que pagó la "
        "casa (premio, importe anulado o cashout) y beneficio = devuelto − apostado. En juego es lo "
        "apostado en las surebets pendientes, igual que en el Bankroll."
    )

    _descarga_pdf(df, patas_originales, rango_fechas)

    for _, casa in resumen.iterrows():
        patas_casa = patas[patas["casa_apuestas"] == casa["casa_apuestas"]].sort_values("fecha_ref", ascending=False)
        en_juego_txt = f" · en juego {casa['en_juego']:,.2f} €" if casa["en_juego"] else ""
        with st.expander(
            f"{casa['casa_apuestas']} · {int(casa['apuestas'])} apuestas · apostado {casa['apostado']:,.2f} € · "
            f"beneficio {casa['beneficio']:+,.2f} €{en_juego_txt}"
        ):
            st.dataframe(
                pd.DataFrame(
                    {
                        "Fecha evento": patas_casa["fecha_ref"].dt.strftime("%Y-%m-%d"),
                        "Evento": patas_casa["evento"],
                        "Mercado": patas_casa["mercado"],
                        "Selección": patas_casa["seleccion"],
                        "Cuota": patas_casa["cuota"],
                        "Importe (€)": patas_casa["importe"].round(2),
                        "Estado": patas_casa["estado"],
                        "Resultado": patas_casa["resultado"],
                        "Devuelto (€)": patas_casa["devuelto"].round(2),
                        "Beneficio (€)": patas_casa["beneficio"].round(2),
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )


def _descarga_pdf(df: pd.DataFrame, patas: pd.DataFrame, rango_fechas: tuple):
    """Botón para descargar en PDF el beneficio de cada casa (solo surebets resueltas),
    con los filtros aplicados, para la declaración de la renta."""
    resueltas = df[df["estado"] == "resuelta"]
    if resueltas.empty:
        st.caption("No hay surebets resueltas con estos filtros para generar el informe PDF.")
        return
    resumen, _ = resumen_por_casa(resueltas, patas)
    desde, hasta = rango_fechas
    nombre = f"beneficio_por_casa_{desde:%Y%m%d}_{hasta:%Y%m%d}.pdf" if desde else "beneficio_por_casa.pdf"
    st.download_button(
        "📄 Descargar informe PDF (beneficio por casa)",
        data=pdf_beneficio_por_casa(resumen, desde, hasta),
        file_name=nombre,
        mime="application/pdf",
        help="Beneficio de cada casa de apuestas en el periodo filtrado, para la declaración de la renta. "
        "Solo cuenta las surebets resueltas.",
    )


def render():
    st.subheader("Historial de apuestas")

    surebets, patas = _cargar_datos()
    if surebets.empty:
        st.info("Todavía no hay surebets registradas. Ve a la pestaña 'Registrar apuesta' para crear la primera.")
        return

    df, patas_filtradas, casa_sel, rango_fechas = _aplicar_filtros(surebets, patas)
    if df.empty:
        st.warning("No hay surebets que coincidan con los filtros seleccionados.")
        return

    tab_surebets, tab_casas = st.tabs(["Surebets", "Por casa de apuestas"])
    with tab_surebets:
        _tabla_resumen(df)
        st.markdown("---")
        _detalle_por_surebet(df, patas_filtradas)
    with tab_casas:
        _resumen_por_casa(df, patas_filtradas, casa_sel, rango_fechas)
