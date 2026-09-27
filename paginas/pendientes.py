# paginas/pendientes.py
"""Pestaña de surebets pendientes de resolver (antes formaba parte de
'Registrar apuesta'; se separó para no mezclar crear apuestas nuevas con
resolver las que ya están en juego)."""

import streamlit as st

import database as db
from calculos import calcular_resultado_real

ICONOS_DEPORTE = {
    "Fútbol": "⚽",
    "Baloncesto": "🏀",
    "Tenis": "🎾",
    "Voleibol": "🏐",
    "Balonmano": "🤾",
    "Tenis de mesa": "🏓",
    "Béisbol": "⚾",
    "Hockey hielo": "🏒",
    "Rugby": "🏉",
    "Boxeo/MMA": "🥊",
    "Fórmula 1/Motor": "🏎️",
    "Esports": "🎮",
}
ICONO_POR_DEFECTO = "🏆"


def render():
    st.subheader("Apuestas pendientes de resolver")

    pendientes = db.listar_surebets_pendientes()
    if not pendientes:
        st.info("No tienes surebets pendientes. ¡Al día!")
        return

    for surebet in pendientes:
        patas = db.listar_patas(surebet["id"])
        icono = ICONOS_DEPORTE.get(surebet["deporte"], ICONO_POR_DEFECTO)
        with st.expander(
            f"{icono} {surebet['fecha']} · {surebet['evento']} · {surebet['mercado']} "
            f"(objetivo: {surebet['beneficio_esperado_importe']:.2f} €)",
            key=f"expander_pendiente_{surebet['id']}",
            on_change="rerun",
        ):
            resultados_seleccionados = {}
            importes_cierre_seleccionados = {}
            opciones_resultado = ["pendiente", "ganada", "perdida", "anulada", "cerrada"]
            for pata in patas:
                with st.container(border=True):
                    st.markdown(f"**{pata['casa_apuestas']}** — {pata['seleccion']}")
                    st.caption(f"Cuota {pata['cuota']:.2f} · Importe apostado {pata['importe']:.2f} €")
                    c1, c2 = st.columns(2)
                    resultado_sel = c1.selectbox(
                        "Resultado",
                        options=opciones_resultado,
                        index=opciones_resultado.index(pata["resultado"]),
                        key=f"resultado_pata_{pata['id']}",
                    )
                    resultados_seleccionados[pata["id"]] = resultado_sel
                    if resultado_sel == "cerrada":
                        importes_cierre_seleccionados[pata["id"]] = c2.number_input(
                            "Importe de cierre (€)",
                            min_value=0.0,
                            step=1.0,
                            format="%.2f",
                            value=float(pata["importe_cierre"] or 0.0),
                            key=f"importe_cierre_pata_{pata['id']}",
                        )
                    else:
                        importes_cierre_seleccionados[pata["id"]] = None

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("✅ Guardar y cerrar", key=f"cerrar_{surebet['id']}", use_container_width=True):
                    if any(r == "pendiente" for r in resultados_seleccionados.values()):
                        st.error("Marca el resultado de todas las patas antes de cerrar la surebet.")
                    else:
                        for pata_id, resultado in resultados_seleccionados.items():
                            db.actualizar_resultado_pata(
                                pata_id, resultado, importes_cierre_seleccionados[pata_id]
                            )
                        datos = [
                            (
                                p["importe"],
                                p["cuota"],
                                resultados_seleccionados[p["id"]],
                                importes_cierre_seleccionados[p["id"]],
                            )
                            for p in patas
                        ]
                        beneficio_real = calcular_resultado_real(datos, surebet["importe_total"])
                        db.cerrar_surebet(surebet["id"], beneficio_real)
                        st.success(f"Surebet cerrada. Beneficio real: {beneficio_real:.2f} €")
                        st.rerun()
            with col_b:
                if st.button("🗑️ Eliminar surebet", key=f"eliminar_{surebet['id']}", use_container_width=True):
                    db.eliminar_surebet(surebet["id"])
                    st.rerun()
