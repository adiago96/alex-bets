# paginas/historial.py
"""Pestaña de historial: listado detallado de cada surebet y cómo quedó cada pata."""

import pandas as pd
import streamlit as st

import database as db


def _cargar_datos():
    surebets, patas = db.obtener_todo_dataframe()
    if not surebets.empty:
        surebets["fecha"] = pd.to_datetime(surebets["fecha"])
    return surebets, patas


TODOS = "Todos"


def _opciones(serie: pd.Series) -> list:
    return [TODOS] + sorted(v for v in serie.dropna().unique() if str(v).strip())


def _aplicar_filtros(surebets: pd.DataFrame, patas: pd.DataFrame):
    col1, col2, col3, col4 = st.columns(4)
    estado_sel = col1.selectbox(
        "Estado", options=[TODOS, "pendiente", "resuelta"], index=2, key="hist_estado_sel",
        format_func=lambda v: v.capitalize(),
    )
    deporte_sel = col2.selectbox("Deporte", options=_opciones(surebets["deporte"]), key="hist_deporte_sel")
    mercado_sel = col3.selectbox("Mercado", options=_opciones(surebets["mercado"]), key="hist_mercado_sel")
    casas = _opciones(patas["casa_apuestas"]) if not patas.empty else [TODOS]
    casa_sel = col4.selectbox("Casa de apuestas", options=casas, key="hist_casa_sel")

    if not surebets.empty:
        fecha_min = surebets["fecha"].min().date()
        fecha_max = surebets["fecha"].max().date()
        rango_fechas = st.date_input(
            "Rango de fechas",
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
            df = df[(df["fecha"].dt.date >= inicio) & (df["fecha"].dt.date <= fin)]

    if casa_sel != TODOS:
        ids_por_casa = set(patas[patas["casa_apuestas"] == casa_sel]["surebet_id"])
        df = df[df["id"].isin(ids_por_casa)]

    patas_filtradas = patas[patas["surebet_id"].isin(df["id"])] if not patas.empty else patas
    return df.sort_values("fecha", ascending=False), patas_filtradas


def _tabla_resumen(df: pd.DataFrame):
    resumen = pd.DataFrame(
        {
            "Fecha": df["fecha"].dt.strftime("%Y-%m-%d"),
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
            f"{estado_icono} {surebet['fecha'].strftime('%Y-%m-%d')} · {surebet['evento']} · "
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


def render():
    st.subheader("Historial de apuestas")

    surebets, patas = _cargar_datos()
    if surebets.empty:
        st.info("Todavía no hay surebets registradas. Ve a la pestaña 'Registrar apuesta' para crear la primera.")
        return

    df, patas_filtradas = _aplicar_filtros(surebets, patas)
    if df.empty:
        st.warning("No hay surebets que coincidan con los filtros seleccionados.")
        return

    _tabla_resumen(df)
    st.markdown("---")
    _detalle_por_surebet(df, patas_filtradas)
