# paginas/registrar.py
"""Pestaña de registro de nuevas surebets y resolución de las pendientes."""

from datetime import date

import pandas as pd
import streamlit as st

import database as db
from calculos import calcular_importe_total_para_beneficio, calcular_resultado_real, calcular_surebet

CASAS_HABITUALES = [
    "Bet365", "Bwin", "Betfair", "William Hill", "Codere",
    "Marathonbet", "Pinnacle", "Betsson", "Winamax", "Luckia", "LeoVegas",
]

MERCADOS_HABITUALES = [
    "1X2",
    "Doble oportunidad",
    "Over/Under goles",
    "Ambos marcan (BTTS)",
    "Hándicap asiático",
    "Hándicap europeo",
    "Córners",
    "Tarjetas",
    "Ganador del partido/set",
    "Hándicap de sets/juegos",
]

# Mercados donde la selección es "Más de X" / "Menos de X" con una línea numérica.
MERCADOS_CON_LINEA = ["Over/Under goles", "Córners", "Tarjetas"]

# Selecciones habituales para el resto de mercados con opciones cerradas.
SELECCIONES_POR_MERCADO = {
    "1X2": ["Local", "Empate", "Visitante"],
    "Doble oportunidad": ["Local o Empate", "Local o Visitante", "Empate o Visitante"],
    "Ambos marcan (BTTS)": ["Sí", "No"],
    "Hándicap asiático": ["Local", "Visitante"],
    "Hándicap europeo": ["Local", "Empate", "Visitante"],
    "Ganador del partido/set": ["Jugador/Equipo 1", "Jugador/Equipo 2"],
    "Hándicap de sets/juegos": ["Jugador/Equipo 1", "Jugador/Equipo 2"],
}


def _init_state():
    if "patas_temp" not in st.session_state:
        st.session_state.patas_temp = [
            {"casa_apuestas": "", "seleccion": "", "cuota": 1.01},
            {"casa_apuestas": "", "seleccion": "", "cuota": 1.01},
        ]
    if "resultado_calculo" not in st.session_state:
        st.session_state.resultado_calculo = None


def _formulario_nueva_surebet():
    st.subheader("Nueva surebet")

    col_a, col_b = st.columns(2)
    with col_a:
        fecha = st.date_input("Fecha", value=date.today())
        evento = st.text_input("Evento", placeholder="Ej. Real Madrid vs Barcelona")
    with col_b:
        mercado = st.selectbox(
            "Mercado",
            options=[""] + MERCADOS_HABITUALES + ["Otro..."],
            index=0,
            key="mercado_select",
        )
        if mercado == "Otro...":
            mercado = st.text_input("Nombre del mercado", key="mercado_otro")
        notas = st.text_input("Notas (opcional)", placeholder="Cualquier detalle relevante")

    st.markdown("**Patas de la surebet** (una fila por casa de apuestas)")

    col_btn1, col_btn2, _ = st.columns([1, 1, 3])
    with col_btn1:
        if st.button("➕ Añadir pata"):
            st.session_state.patas_temp.append({"casa_apuestas": "", "seleccion": "", "cuota": 1.01})
    with col_btn2:
        if st.button("➖ Quitar última pata") and len(st.session_state.patas_temp) > 2:
            st.session_state.patas_temp.pop()

    for i, pata in enumerate(st.session_state.patas_temp):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            pata["casa_apuestas"] = st.selectbox(
                f"Casa de apuestas #{i + 1}",
                options=[""] + CASAS_HABITUALES + ["Otra..."],
                index=0,
                key=f"casa_{i}",
            )
            if pata["casa_apuestas"] == "Otra...":
                pata["casa_apuestas"] = st.text_input("Nombre de la casa", key=f"casa_otra_{i}")
        with c2:
            if mercado in MERCADOS_CON_LINEA:
                sub1, sub2 = st.columns([1, 1])
                tipo_linea = sub1.selectbox(
                    f"Tipo #{i + 1}", options=["Más de", "Menos de"], key=f"seleccion_tipo_{i}"
                )
                linea = sub2.number_input(
                    f"Línea #{i + 1}", min_value=0.0, step=0.5, format="%.2f", key=f"seleccion_linea_{i}"
                )
                pata["seleccion"] = f"{tipo_linea} {linea:g}"
            elif mercado in SELECCIONES_POR_MERCADO:
                opciones = SELECCIONES_POR_MERCADO[mercado] + ["Otra..."]
                seleccionada = st.selectbox(
                    f"Selección #{i + 1}", options=opciones, key=f"seleccion_select_{i}"
                )
                if seleccionada == "Otra...":
                    pata["seleccion"] = st.text_input(
                        f"Selección #{i + 1} (personalizada)", key=f"seleccion_otra_{i}"
                    )
                else:
                    pata["seleccion"] = seleccionada
            else:
                pata["seleccion"] = st.text_input(
                    f"Selección #{i + 1}", placeholder="Ej. Local, Más de 2.5...", key=f"seleccion_{i}"
                )
        with c3:
            pata["cuota"] = st.number_input(
                f"Cuota #{i + 1}", min_value=1.01, step=0.01, format="%.2f", key=f"cuota_{i}"
            )

    st.markdown("---")
    st.markdown("**Modo de cálculo del reparto**")
    modo = st.radio(
        "¿Cómo quieres calcular los importes?",
        options=["Importe total a invertir", "Beneficio garantizado deseado"],
        horizontal=True,
    )

    if modo == "Importe total a invertir":
        importe_total = st.number_input("Importe total a repartir (€)", min_value=1.0, value=100.0, step=1.0)
        beneficio_objetivo = None
    else:
        beneficio_objetivo = st.number_input("Beneficio garantizado deseado (€)", min_value=0.01, value=10.0, step=1.0)
        importe_total = None

    if st.button("🧮 Calcular reparto", type="primary"):
        cuotas = [p["cuota"] for p in st.session_state.patas_temp]
        try:
            if modo == "Beneficio garantizado deseado":
                importe_total = calcular_importe_total_para_beneficio(cuotas, beneficio_objetivo)
            resultado = calcular_surebet(cuotas, importe_total)
            st.session_state.resultado_calculo = {
                "resultado": resultado,
                "importe_total": importe_total,
                "fecha": fecha,
                "evento": evento,
                "mercado": mercado,
                "notas": notas,
            }
        except ValueError as e:
            st.session_state.resultado_calculo = None
            st.error(str(e))

    resultado_info = st.session_state.resultado_calculo
    if resultado_info:
        resultado = resultado_info["resultado"]
        confirmar_riesgo = True
        if not resultado.es_arbitraje:
            confirmar_riesgo = False
            st.error(
                f"🚫 ¡Cuidado! Estas cuotas NO forman una surebet real (probabilidad implícita total: "
                f"{resultado.probabilidad_implicita_total * 100:.2f}% ≥ 100%). "
                f"Con este reparto **perderías {abs(resultado.beneficio_garantizado):.2f} €** "
                f"pase lo que pase, así que no hay beneficio garantizado."
            )
            confirmar_riesgo = st.checkbox(
                "Entiendo el riesgo y quiero guardar esta apuesta de todas formas",
                key="confirmar_riesgo",
            )
        else:
            st.success(
                f"✅ Surebet válida. Margen garantizado: **{resultado.margen_pct:.2f}%** · "
                f"Beneficio garantizado: **{resultado.beneficio_garantizado:.2f} €**"
            )

        tabla = pd.DataFrame(
            {
                "Casa de apuestas": [p["casa_apuestas"] for p in st.session_state.patas_temp],
                "Selección": [p["seleccion"] for p in st.session_state.patas_temp],
                "Cuota": [p["cuota"] for p in st.session_state.patas_temp],
                "Importe a apostar (€)": [round(x, 2) for x in resultado.importes],
            }
        )
        st.dataframe(tabla, use_container_width=True, hide_index=True)
        st.caption(
            f"Importe total: {resultado_info['importe_total']:.2f} € · "
            f"Retorno garantizado: {resultado.retorno_garantizado:.2f} €"
        )

        if st.button("💾 Guardar surebet", disabled=not confirmar_riesgo):
            patas_guardar = [
                {
                    "casa_apuestas": p["casa_apuestas"],
                    "seleccion": p["seleccion"],
                    "cuota": p["cuota"],
                    "importe": importe,
                }
                for p, importe in zip(st.session_state.patas_temp, resultado.importes)
            ]
            if any(not p["casa_apuestas"] for p in patas_guardar):
                st.error("Todas las patas necesitan una casa de apuestas.")
            elif not resultado_info["evento"] or not resultado_info["mercado"]:
                st.error("Evento y mercado son obligatorios.")
            else:
                db.crear_surebet(
                    fecha=resultado_info["fecha"].isoformat(),
                    evento=resultado_info["evento"],
                    mercado=resultado_info["mercado"],
                    importe_total=resultado_info["importe_total"],
                    beneficio_pct=resultado.margen_pct,
                    beneficio_importe=resultado.beneficio_garantizado,
                    notas=resultado_info["notas"],
                    patas=patas_guardar,
                )
                st.session_state.patas_temp = [
                    {"casa_apuestas": "", "seleccion": "", "cuota": 1.01},
                    {"casa_apuestas": "", "seleccion": "", "cuota": 1.01},
                ]
                st.session_state.resultado_calculo = None
                st.success("Surebet guardada correctamente.")
                st.rerun()


def _resolver_pendientes():
    st.subheader("Apuestas pendientes de resolver")

    pendientes = db.listar_surebets_pendientes()
    if not pendientes:
        st.info("No tienes surebets pendientes. ¡Al día!")
        return

    for surebet in pendientes:
        patas = db.listar_patas(surebet["id"])
        with st.expander(
            f"{surebet['fecha']} · {surebet['evento']} · {surebet['mercado']} "
            f"(objetivo: {surebet['beneficio_esperado_importe']:.2f} €)"
        ):
            resultados_seleccionados = {}
            for pata in patas:
                col1, col2, col3, col4 = st.columns([2, 2, 1, 1.5])
                col1.write(pata["casa_apuestas"])
                col2.write(pata["seleccion"])
                col3.write(f"Cuota {pata['cuota']:.2f} · {pata['importe']:.2f} €")
                resultados_seleccionados[pata["id"]] = col4.selectbox(
                    "Resultado",
                    options=["pendiente", "ganada", "perdida"],
                    index=["pendiente", "ganada", "perdida"].index(pata["resultado"]),
                    key=f"resultado_pata_{pata['id']}",
                    label_visibility="collapsed",
                )

            col_a, col_b = st.columns([1, 3])
            with col_a:
                if st.button("Guardar y cerrar", key=f"cerrar_{surebet['id']}"):
                    if any(r == "pendiente" for r in resultados_seleccionados.values()):
                        st.error("Marca el resultado de todas las patas antes de cerrar la surebet.")
                    else:
                        for pata_id, resultado in resultados_seleccionados.items():
                            db.actualizar_resultado_pata(pata_id, resultado)
                        datos = [
                            (p["importe"], p["cuota"], resultados_seleccionados[p["id"]]) for p in patas
                        ]
                        beneficio_real = calcular_resultado_real(datos, surebet["importe_total"])
                        db.cerrar_surebet(surebet["id"], beneficio_real)
                        st.success(f"Surebet cerrada. Beneficio real: {beneficio_real:.2f} €")
                        st.rerun()
            with col_b:
                if st.button("🗑️ Eliminar surebet", key=f"eliminar_{surebet['id']}"):
                    db.eliminar_surebet(surebet["id"])
                    st.rerun()


def render():
    _init_state()
    _formulario_nueva_surebet()
    st.markdown("---")
    _resolver_pendientes()
