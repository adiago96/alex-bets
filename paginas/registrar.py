# paginas/registrar.py
"""Pestaña de registro de nuevas surebets y resolución de las pendientes."""

from datetime import date

import pandas as pd
import streamlit as st

import database as db
from calculos import (
    calcular_beneficios_por_seleccion,
    calcular_importe_total_para_beneficio_agrupado,
    calcular_reparto_desde_grupo_fijo,
    calcular_resultado_real,
    calcular_sugerencia_agrupada,
)

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

# Mercados de hándicap: la selección es un lado + el valor del hándicap (puede
# ser distinto en cada casa, p.ej. -4.5 en una y +3.5 en otra para jugar una middle).
MERCADOS_CON_HANDICAP = {
    "Hándicap asiático": ["Local", "Visitante"],
    "Hándicap europeo": ["Local", "Empate", "Visitante"],
    "Hándicap de sets/juegos": ["Jugador/Equipo 1", "Jugador/Equipo 2"],
}

# Selecciones habituales para el resto de mercados con opciones cerradas.
SELECCIONES_POR_MERCADO = {
    "1X2": ["Local", "Empate", "Visitante"],
    "Doble oportunidad": ["Local o Empate", "Local o Visitante", "Empate o Visitante"],
    "Ambos marcan (BTTS)": ["Sí", "No"],
    "Ganador del partido/set": ["Jugador/Equipo 1", "Jugador/Equipo 2"],
}


def _init_state():
    if "patas_temp" not in st.session_state:
        st.session_state.patas_temp = [
            {"casa_apuestas": "", "seleccion": "", "cuota": 1.01},
            {"casa_apuestas": "", "seleccion": "", "cuota": 1.01},
        ]


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

    num_patas = len(st.session_state.patas_temp)

    st.markdown("---")
    st.markdown("**Sugerencia de importes** (opcional, siempre puedes escribir el importe a mano en cada pata)")
    modo = st.radio(
        "¿Cómo quieres que se calcule la sugerencia?",
        options=[
            "Importe total a invertir",
            "Beneficio garantizado deseado",
            "Fijar el importe de una pata (p.ej. límite de una casa)",
            "Sin sugerencia, importes manuales",
        ],
    )

    # Cuotas, selecciones e importes "frescos": si el usuario acaba de tocar un
    # campo, session_state ya tiene el valor nuevo aunque el widget de la pata
    # todavía no se haya vuelto a dibujar en esta ejecución.
    cuotas = [
        st.session_state.get(f"cuota_{i}", p.get("cuota", 1.01))
        for i, p in enumerate(st.session_state.patas_temp)
    ]
    selecciones = [p.get("seleccion", "") for p in st.session_state.patas_temp]
    importes_actuales = [
        st.session_state.get(f"importe_{i}", p.get("importe", 0.0)) or 0.0
        for i, p in enumerate(st.session_state.patas_temp)
    ]

    idx_fijo = None
    if modo == "Importe total a invertir":
        importe_total_objetivo = st.number_input("Importe total a repartir (€)", min_value=1.0, value=100.0, step=1.0)
    elif modo == "Beneficio garantizado deseado":
        beneficio_objetivo = st.number_input("Beneficio garantizado deseado (€)", min_value=0.01, value=10.0, step=1.0)
    elif modo == "Fijar el importe de una pata (p.ej. límite de una casa)":
        opciones_pata = [
            f"Pata #{i + 1}" + (f" - {p['casa_apuestas']}" if p["casa_apuestas"] else "")
            for i, p in enumerate(st.session_state.patas_temp)
        ]
        pata_elegida = st.selectbox("¿Qué pata quieres fijar?", options=opciones_pata)
        idx_fijo = opciones_pata.index(pata_elegida)
        st.caption(
            "Escribe el importe de esa pata (y, si la has repartido en más de una casa "
            "por límite, en las demás patas con la misma selección) en la tabla de abajo."
        )

    suggested_importes = None
    error_sugerencia = None
    try:
        if modo == "Importe total a invertir":
            suggested_importes = calcular_sugerencia_agrupada(selecciones, cuotas, importe_total_objetivo)
        elif modo == "Beneficio garantizado deseado":
            importe_total_calc = calcular_importe_total_para_beneficio_agrupado(
                selecciones, cuotas, beneficio_objetivo
            )
            suggested_importes = calcular_sugerencia_agrupada(selecciones, cuotas, importe_total_calc)
        elif modo == "Fijar el importe de una pata (p.ej. límite de una casa)":
            suggested_importes = calcular_reparto_desde_grupo_fijo(
                selecciones, cuotas, importes_actuales, idx_fijo
            )
    except ValueError as e:
        error_sugerencia = str(e)

    if error_sugerencia:
        st.warning(f"No se puede calcular la sugerencia: {error_sugerencia}")

    if suggested_importes is not None and st.button("🪄 Aplicar sugerencia a todas las patas"):
        for i, importe in enumerate(suggested_importes):
            if importe is not None:
                st.session_state[f"importe_{i}"] = round(importe, 2)
        st.rerun()

    st.markdown("**Patas de la surebet** (una fila por casa de apuestas)")

    for i, pata in enumerate(st.session_state.patas_temp):
        c1, c2, c3, c4 = st.columns([2, 2, 1, 1.3])
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
            elif mercado in MERCADOS_CON_HANDICAP:
                sub1, sub2 = st.columns([1, 1])
                lado = sub1.selectbox(
                    f"Lado #{i + 1}", options=MERCADOS_CON_HANDICAP[mercado], key=f"seleccion_lado_{i}"
                )
                linea = sub2.number_input(
                    f"Hándicap #{i + 1}", step=0.25, format="%.2f", key=f"seleccion_handicap_{i}"
                )
                pata["seleccion"] = f"{lado} {linea:+g}"
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
        with c4:
            pata["importe"] = st.number_input(
                f"Importe (€) #{i + 1}", min_value=0.0, step=1.0, format="%.2f", key=f"importe_{i}"
            )
            sugerido_i = suggested_importes[i] if suggested_importes is not None else None
            if sugerido_i is None and suggested_importes is not None:
                st.caption("🔒 Pata de referencia (fijada a mano)")
            elif sugerido_i is not None and sugerido_i == 0.0 and selecciones.count(selecciones[i]) > 1:
                st.caption("💡 Sugerido: 0.00 € (ya cubierto por otra pata con la misma selección)")
            elif sugerido_i is not None:
                st.caption(f"💡 Sugerido: {sugerido_i:.2f} €")

    importes = [p["importe"] for p in st.session_state.patas_temp]
    cuotas_finales = [p["cuota"] for p in st.session_state.patas_temp]
    selecciones_finales = [p["seleccion"] for p in st.session_state.patas_temp]
    importe_total = sum(importes)

    confirmar_riesgo = True
    if importe_total > 0:
        beneficios = calcular_beneficios_por_seleccion(selecciones_finales, cuotas_finales, importes)
        peor_beneficio = min(beneficios)

        tabla = pd.DataFrame(
            {
                "Casa de apuestas": [p["casa_apuestas"] for p in st.session_state.patas_temp],
                "Selección": [p["seleccion"] for p in st.session_state.patas_temp],
                "Cuota": [p["cuota"] for p in st.session_state.patas_temp],
                "Importe a apostar (€)": [round(x, 2) for x in importes],
                "Si gana esta pata, beneficio (€)": [round(b, 2) for b in beneficios],
            }
        )
        st.dataframe(tabla, use_container_width=True, hide_index=True)
        st.caption(f"Importe total: {importe_total:.2f} €")

        if peor_beneficio > 0:
            st.success(
                f"✅ Surebet válida en el peor de los casos. Beneficio garantizado mínimo: "
                f"**{peor_beneficio:.2f} €** ({peor_beneficio / importe_total * 100:.2f}%)"
            )
        else:
            confirmar_riesgo = False
            st.error(
                f"🚫 ¡Cuidado! Con estos importes hay al menos un resultado en el que "
                f"**perderías {abs(peor_beneficio):.2f} €**, no hay beneficio garantizado en todos los casos."
            )
            confirmar_riesgo = st.checkbox(
                "Entiendo el riesgo y quiero guardar esta apuesta de todas formas",
                key="confirmar_riesgo",
            )
    else:
        beneficios = None
        peor_beneficio = 0.0
        st.info("Escribe el importe a apostar en cada pata para ver el resultado esperado.")

    if st.button("💾 Guardar surebet", type="primary", disabled=not confirmar_riesgo or importe_total <= 0):
        patas_guardar = [
            {
                "casa_apuestas": p["casa_apuestas"],
                "seleccion": p["seleccion"],
                "cuota": p["cuota"],
                "importe": p["importe"],
            }
            for p in st.session_state.patas_temp
        ]
        if any(not p["casa_apuestas"] for p in patas_guardar):
            st.error("Todas las patas necesitan una casa de apuestas.")
        elif any(p["importe"] <= 0 for p in patas_guardar):
            st.error("Todas las patas necesitan un importe a apostar mayor que 0.")
        elif not evento or not mercado:
            st.error("Evento y mercado son obligatorios.")
        else:
            db.crear_surebet(
                fecha=fecha.isoformat(),
                evento=evento,
                mercado=mercado,
                importe_total=importe_total,
                beneficio_pct=(peor_beneficio / importe_total * 100) if importe_total else 0.0,
                beneficio_importe=peor_beneficio,
                notas=notas,
                patas=patas_guardar,
            )
            for i in range(num_patas):
                st.session_state.pop(f"importe_{i}", None)
            st.session_state.patas_temp = [
                {"casa_apuestas": "", "seleccion": "", "cuota": 1.01},
                {"casa_apuestas": "", "seleccion": "", "cuota": 1.01},
            ]
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
