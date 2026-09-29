# paginas/pendientes.py
"""Pestaña de surebets pendientes de resolver (antes formaba parte de
'Registrar apuesta'; se separó para no mezclar crear apuestas nuevas con
resolver las que ya están en juego)."""

from datetime import date, datetime

import streamlit as st

import database as db
from calculos import calcular_resultado_real

ICONOS_DEPORTE = {
    "Fútbol": "⚽",
    "Fútbol Americano": "🏈",
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


def _texto_fecha_evento(surebet):
    """Fecha y hora del partido para la cabecera; las apuestas antiguas, sin
    fecha de evento, muestran la fecha de la apuesta."""
    if surebet["fecha_evento"]:
        return datetime.strptime(surebet["fecha_evento"], "%Y-%m-%d %H:%M").strftime("🗓️ %d/%m/%Y %H:%M")
    return f"{surebet['fecha']} (sin hora del evento)"


def _editor_fecha_evento(surebet):
    """Permite poner o corregir la fecha y hora del evento de una apuesta ya
    guardada (sobre todo las registradas antes de existir el campo)."""
    if surebet["fecha_evento"]:
        actual = datetime.strptime(surebet["fecha_evento"], "%Y-%m-%d %H:%M")
        fecha_defecto, hora_defecto = actual.date(), actual.time()
    else:
        fecha_defecto, hora_defecto = date.fromisoformat(surebet["fecha"][:10]), None
    c1, c2, c3 = st.columns([2, 2, 2], vertical_alignment="bottom")
    fecha_ev = c1.date_input("Fecha del evento", value=fecha_defecto, key=f"fecha_evento_{surebet['id']}")
    hora_ev = c2.time_input("Hora del evento", value=hora_defecto, step=300, key=f"hora_evento_{surebet['id']}")
    if c3.button("🕒 Guardar fecha y hora", key=f"guardar_fecha_evento_{surebet['id']}", use_container_width=True):
        if hora_ev is None:
            st.error("Indica la hora del evento.")
        else:
            db.actualizar_fecha_evento(
                surebet["id"], datetime.combine(fecha_ev, hora_ev).strftime("%Y-%m-%d %H:%M")
            )
            st.rerun()


def render():
    st.subheader("Apuestas pendientes de resolver")

    pendientes = db.listar_surebets_pendientes()
    if not pendientes:
        st.info("No tienes surebets pendientes. ¡Al día!")
        return

    st.caption(
        "Ordenadas por fecha y hora del evento, las más recientes arriba. Al guardar y cerrar, el "
        "importe de cada pata sale de 'en juego' y entra en el líquido de su casa lo que devuelve: "
        "ganada → importe × cuota, anulada → el importe, cerrada → el importe de cierre, perdida → nada."
    )

    for surebet in pendientes:
        patas = db.listar_patas(surebet["id"])
        icono = ICONOS_DEPORTE.get(surebet["deporte"], ICONO_POR_DEFECTO)
        with st.expander(
            f"{icono} {_texto_fecha_evento(surebet)} · {surebet['evento']} · {surebet['mercado']} "
            f"(objetivo: {surebet['beneficio_esperado_importe']:.2f} €)",
            key=f"expander_pendiente_{surebet['id']}",
            on_change="rerun",
        ):
            _editor_fecha_evento(surebet)
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
                if st.button(
                    "🗑️ Eliminar surebet",
                    key=f"eliminar_{surebet['id']}",
                    use_container_width=True,
                    help="Para una apuesta que no llegaste a hacer: el importe de cada pata sale de "
                    "'en juego' y vuelve al líquido de su casa.",
                ):
                    db.eliminar_surebet(surebet["id"])
                    st.rerun()
