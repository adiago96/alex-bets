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


def _aplicar_filtros(surebets: pd.DataFrame, patas: pd.DataFrame):
    col1, col2, col3 = st.columns(3)
    estados = col1.multiselect(
        "Estado", options=["pendiente", "resuelta"], default=["resuelta"], key="hist_estado"
    )
    mercados = sorted(surebets["mercado"].unique()) if not surebets.empty else []
    mercados_sel = col2.multiselect("Mercado", options=mercados, default=mercados, key="hist_mercado")
    casas = sorted(patas["casa_apuestas"].unique()) if not patas.empty else []
    casas_sel = col3.multiselect("Casa de apuestas", options=casas, default=casas, key="hist_casa")

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
        df = df[df["estado"].isin(estados)]
        df = df[df["mercado"].isin(mercados_sel)]
        if rango_fechas and len(rango_fechas) == 2:
            inicio, fin = rango_fechas
            df = df[(df["fecha"].dt.date >= inicio) & (df["fecha"].dt.date <= fin)]

    ids_por_casa = set(patas[patas["casa_apuestas"].isin(casas_sel)]["surebet_id"]) if not patas.empty else set()
    if casas_sel:
        df = df[df["id"].isin(ids_por_casa)]

    patas_filtradas = patas[patas["surebet_id"].isin(df["id"])] if not patas.empty else patas
    return df.sort_values("fecha", ascending=False), patas_filtradas


def _tabla_resumen(df: pd.DataFrame):
    resumen = pd.DataFrame(
        {
            "Fecha": df["fecha"].dt.strftime("%Y-%m-%d"),
            "Evento": df["evento"],
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
            f"{surebet['mercado']} · {beneficio_txt}"
        ):
            tabla_patas = patas_surebet[["casa_apuestas", "seleccion", "cuota", "importe", "resultado"]].rename(
                columns={
                    "casa_apuestas": "Casa de apuestas",
                    "seleccion": "Selección",
                    "cuota": "Cuota",
                    "importe": "Importe (€)",
                    "resultado": "Resultado",
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
