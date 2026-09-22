# paginas/dashboard.py
"""Pestaña de dashboard: totales, ROI y análisis por casa de apuestas / mercado."""

import pandas as pd
import plotly.express as px
import streamlit as st

import database as db

COLOR_GANANCIA = "#2ecc71"
COLOR_PERDIDA = "#e74c3c"

MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


def _cargar_datos():
    surebets, patas = db.obtener_todo_dataframe()
    if not surebets.empty:
        surebets["fecha"] = pd.to_datetime(surebets["fecha"])
    return surebets, patas


def _aplicar_filtros(surebets: pd.DataFrame, patas: pd.DataFrame):
    st.sidebar.header("Filtros")

    estados = st.sidebar.multiselect(
        "Estado", options=["pendiente", "resuelta"], default=["pendiente", "resuelta"]
    )
    mercados = sorted(surebets["mercado"].unique()) if not surebets.empty else []
    mercados_sel = st.sidebar.multiselect("Mercado", options=mercados, default=mercados)

    casas = sorted(patas["casa_apuestas"].unique()) if not patas.empty else []
    casas_sel = st.sidebar.multiselect("Casa de apuestas", options=casas, default=casas)

    if not surebets.empty:
        fecha_min = surebets["fecha"].min().date()
        fecha_max = surebets["fecha"].max().date()
        rango_fechas = st.sidebar.date_input(
            "Rango de fechas", value=(fecha_min, fecha_max), min_value=fecha_min, max_value=fecha_max
        )
        anios_presentes = sorted(surebets["fecha"].dt.year.unique(), reverse=True)
        anios_sel = st.sidebar.multiselect("Año", options=anios_presentes, default=anios_presentes)
        meses_presentes = sorted(surebets["fecha"].dt.month.unique())
        meses_sel = st.sidebar.multiselect(
            "Mes", options=meses_presentes, default=meses_presentes, format_func=lambda m: MESES_ES[m]
        )
    else:
        rango_fechas = None
        anios_sel, meses_sel = [], []

    df = surebets.copy()
    if not df.empty:
        df = df[df["estado"].isin(estados)]
        df = df[df["mercado"].isin(mercados_sel)]
        if rango_fechas and len(rango_fechas) == 2:
            inicio, fin = rango_fechas
            df = df[(df["fecha"].dt.date >= inicio) & (df["fecha"].dt.date <= fin)]
        df = df[df["fecha"].dt.year.isin(anios_sel)]
        df = df[df["fecha"].dt.month.isin(meses_sel)]

    ids_por_casa = set(patas[patas["casa_apuestas"].isin(casas_sel)]["surebet_id"]) if not patas.empty else set()
    if casas_sel:
        df = df[df["id"].isin(ids_por_casa)]

    patas_filtradas = patas[patas["surebet_id"].isin(df["id"])] if not patas.empty else patas
    return df, patas_filtradas


def _kpis(df: pd.DataFrame):
    resueltas = df[df["estado"] == "resuelta"]
    pendientes = df[df["estado"] == "pendiente"]

    total_apostado = resueltas["importe_total"].sum()
    beneficio_total = resueltas["beneficio_real"].sum()
    roi = (beneficio_total / total_apostado * 100) if total_apostado else 0.0
    beneficio_medio = resueltas["beneficio_real"].mean() if not resueltas.empty else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total apostado", f"{total_apostado:,.2f} €")
    c2.metric("Beneficio total", f"{beneficio_total:,.2f} €")
    c3.metric("ROI", f"{roi:,.2f} %")
    c4.metric("Beneficio medio / surebet", f"{beneficio_medio:,.2f} €")
    c5.metric("Resueltas / Pendientes", f"{len(resueltas)} / {len(pendientes)}")


def _grafico_evolucion(df: pd.DataFrame):
    resueltas = df[df["estado"] == "resuelta"].sort_values("fecha")
    if resueltas.empty:
        st.info("Todavía no hay surebets resueltas para mostrar la evolución.")
        return
    resueltas = resueltas.copy()
    resueltas["beneficio_acumulado"] = resueltas["beneficio_real"].cumsum()
    fig = px.line(
        resueltas, x="fecha", y="beneficio_acumulado", markers=True,
        title="Beneficio acumulado en el tiempo",
        labels={"fecha": "Fecha", "beneficio_acumulado": "Beneficio acumulado (€)"},
    )
    fig.update_traces(line_color=COLOR_GANANCIA)
    st.plotly_chart(fig, use_container_width=True)


def _resumen_mensual(df: pd.DataFrame):
    resueltas = df[df["estado"] == "resuelta"].copy()
    if resueltas.empty:
        st.info("Todavía no hay surebets resueltas en el periodo filtrado para el resumen mensual.")
        return

    resueltas["periodo"] = resueltas["fecha"].dt.to_period("M")
    resumen = resueltas.groupby("periodo").agg(
        apostado=("importe_total", "sum"),
        beneficio=("beneficio_real", "sum"),
        num_surebets=("id", "count"),
    ).reset_index().sort_values("periodo")
    resumen["roi_pct"] = (resumen["beneficio"] / resumen["apostado"] * 100).round(2)
    resumen["etiqueta"] = resumen["periodo"].apply(lambda p: f"{MESES_ES[p.month]} {p.year}")

    fig = px.bar(
        resumen, x="etiqueta", y="beneficio", title="Beneficio por mes",
        labels={"etiqueta": "Mes", "beneficio": "Beneficio (€)"},
        color="beneficio", color_continuous_scale=[COLOR_PERDIDA, COLOR_GANANCIA],
    )
    st.plotly_chart(fig, use_container_width=True)

    tabla = resumen.sort_values("periodo", ascending=False)[
        ["etiqueta", "apostado", "beneficio", "roi_pct", "num_surebets"]
    ].rename(
        columns={
            "etiqueta": "Mes",
            "apostado": "Apostado (€)",
            "beneficio": "Beneficio (€)",
            "roi_pct": "ROI (%)",
            "num_surebets": "Nº surebets",
        }
    )
    st.dataframe(
        tabla.style.format({"Apostado (€)": "{:.2f}", "Beneficio (€)": "{:.2f}", "ROI (%)": "{:.2f}"}),
        use_container_width=True, hide_index=True,
    )


def _grafico_por_casa(patas: pd.DataFrame, surebets: pd.DataFrame):
    resueltas_ids = set(surebets[surebets["estado"] == "resuelta"]["id"])
    df = patas[
        patas["surebet_id"].isin(resueltas_ids) & patas["resultado"].isin(["ganada", "perdida", "cerrada"])
    ].copy()
    if df.empty:
        st.info("Todavía no hay patas resueltas para analizar por casa de apuestas.")
        return

    def _neto(r):
        if r["resultado"] == "ganada":
            return r["importe"] * (r["cuota"] - 1)
        if r["resultado"] == "cerrada":
            return (r["importe_cierre"] or 0.0) - r["importe"]
        return -r["importe"]

    df["neto"] = df.apply(_neto, axis=1)
    resumen = df.groupby("casa_apuestas").agg(
        beneficio_neto=("neto", "sum"),
        importe_movido=("importe", "sum"),
        num_apuestas=("id", "count"),
    ).reset_index().sort_values("beneficio_neto", ascending=False)

    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(
            resumen, x="casa_apuestas", y="beneficio_neto", title="Beneficio neto por casa de apuestas",
            labels={"casa_apuestas": "Casa de apuestas", "beneficio_neto": "Beneficio neto (€)"},
            color="beneficio_neto", color_continuous_scale=[COLOR_PERDIDA, COLOR_GANANCIA],
        )
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.dataframe(
            resumen.rename(columns={
                "casa_apuestas": "Casa de apuestas",
                "beneficio_neto": "Beneficio neto (€)",
                "importe_movido": "Importe movido (€)",
                "num_apuestas": "Nº apuestas",
            }),
            use_container_width=True, hide_index=True,
        )


def _grafico_por_mercado(df: pd.DataFrame):
    resueltas = df[df["estado"] == "resuelta"]
    if resueltas.empty:
        return
    resumen = resueltas.groupby("mercado").agg(
        beneficio_total=("beneficio_real", "sum"),
        num_surebets=("id", "count"),
    ).reset_index()
    fig = px.pie(
        resumen, names="mercado", values="num_surebets",
        title="Distribución de surebets por mercado",
    )
    st.plotly_chart(fig, use_container_width=True)


def render():
    surebets, patas = _cargar_datos()
    if surebets.empty:
        st.info("Todavía no hay surebets registradas. Ve a la pestaña 'Registrar apuesta' para crear la primera.")
        return

    df, patas_filtradas = _aplicar_filtros(surebets, patas)

    if df.empty:
        st.warning("No hay datos que coincidan con los filtros seleccionados.")
        return

    _kpis(df)
    st.markdown("---")
    st.subheader("Resumen por mes")
    _resumen_mensual(df)
    st.markdown("---")
    _grafico_evolucion(df)
    st.markdown("---")
    _grafico_por_casa(patas_filtradas, df)
    st.markdown("---")
    _grafico_por_mercado(df)

    with st.expander("Ver datos en bruto"):
        st.dataframe(df.sort_values("fecha", ascending=False), use_container_width=True, hide_index=True)
