# paginas/registrar.py
"""Pestaña de registro de nuevas surebets (ver 'pendientes.py' para resolverlas)."""

import unicodedata
from datetime import date, datetime

import pandas as pd
import streamlit as st

import database as db
from calculos import (
    calcular_beneficios_por_seleccion,
    calcular_importe_total_para_beneficio_agrupado,
    calcular_reparto_desde_grupo_fijo,
    calcular_sugerencia_agrupada,
)

DEPORTES_HABITUALES = [
    "Fútbol",
    "Fútbol Americano",
    "Baloncesto",
    "Tenis",
    "Voleibol",
    "Balonmano",
    "Tenis de mesa",
    "Béisbol",
    "Hockey hielo",
    "Rugby",
    "Boxeo/MMA",
    "Fórmula 1/Motor",
    "Esports",
]

# Mercados por deporte. Son categorías genéricas a propósito: "Over/Under"
# vale igual para goles, córners, tarjetas, puntos o recepciones de un
# jugador, y "Hándicap" para cualquier hándicap (asiático, europeo, de goles,
# de córners...). Así el registro es más rápido y el historial no se llena de
# subdivisiones. Si el deporte es "Otro..." o no está en esta lista, se
# ofrecen todos los mercados.
_MERCADOS_DUELO = ["Ganador", "Over/Under", "Hándicap"]
_MERCADOS_CON_EMPATE = ["1X2", "Doble oportunidad", "Over/Under", "Hándicap"]
MERCADOS_POR_DEPORTE = {
    "Fútbol": _MERCADOS_CON_EMPATE + ["Ambos marcan (BTTS)"],
    "Fútbol Americano": _MERCADOS_DUELO,
    "Baloncesto": _MERCADOS_DUELO,
    "Tenis": _MERCADOS_DUELO,
    "Voleibol": _MERCADOS_DUELO,
    "Balonmano": _MERCADOS_CON_EMPATE,
    "Tenis de mesa": _MERCADOS_DUELO,
    "Béisbol": _MERCADOS_DUELO,
    "Hockey hielo": _MERCADOS_CON_EMPATE,
    "Rugby": _MERCADOS_CON_EMPATE,
    "Boxeo/MMA": ["Ganador", "Over/Under", "Irá a decisión"],
    "Fórmula 1/Motor": ["Ganador", "Podio"],
    "Esports": _MERCADOS_DUELO,
}

# Todos los mercados conocidos, para cuando el deporte no está en la lista de
# arriba (p.ej. se escribió a mano en "Otro...").
MERCADOS_HABITUALES = list(dict.fromkeys(m for mercados in MERCADOS_POR_DEPORTE.values() for m in mercados))

# Mercado donde la selección es "Más de X" / "Menos de X" con una línea numérica.
MERCADO_CON_LINEA = "Over/Under"

# Mercado de hándicap: la selección es un lado + el valor del hándicap (puede
# ser distinto en cada casa, p.ej. -4.5 en una y +3.5 en otra para jugar una middle).
MERCADO_CON_HANDICAP = "Hándicap"

# Cómo se llaman los dos lados de un enfrentamiento según el deporte (para
# "Ganador" y "Hándicap"). En fútbol el hándicap admite también "Empate" por
# el hándicap europeo.
_LADOS_POR_DEPORTE = {
    "Tenis": ["Jugador 1", "Jugador 2"],
    "Tenis de mesa": ["Jugador 1", "Jugador 2"],
    "Boxeo/MMA": ["Peleador 1", "Peleador 2"],
    "Esports": ["Equipo 1", "Equipo 2"],
}
_LADOS_POR_DEFECTO = ["Local", "Visitante"]


def _lados(deporte, mercado):
    lados = _LADOS_POR_DEPORTE.get(deporte, _LADOS_POR_DEFECTO)
    if mercado == MERCADO_CON_HANDICAP and deporte == "Fútbol":
        return ["Local", "Empate", "Visitante"]
    return lados


# Selecciones habituales para el resto de mercados con opciones cerradas.
SELECCIONES_POR_MERCADO = {
    "1X2": ["Local", "Empate", "Visitante"],
    "Doble oportunidad": ["Local o Empate", "Local o Visitante", "Empate o Visitante"],
    "Ambos marcan (BTTS)": ["Sí", "No"],
    "Irá a decisión": ["Sí", "No"],
}


def _selecciones_cerradas(deporte, mercado):
    if mercado == "Ganador" and deporte != "Fórmula 1/Motor":
        return _lados(deporte, mercado)
    return SELECCIONES_POR_MERCADO.get(mercado)


# Prefijos de las claves de session_state que dependen del mercado elegido:
# hay que limpiarlas cuando cambia el deporte o el mercado para que no se
# quede guardado un valor que ya no es una opción válida del nuevo desplegable.
_PREFIJOS_SELECCION_PATA = [
    "seleccion_", "seleccion_tipo_", "seleccion_linea_",
    "seleccion_lado_", "seleccion_handicap_", "seleccion_select_", "seleccion_otra_",
]



def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()


def _normalizar_deporte(texto: str) -> str:
    """Quita espacios sobrantes y, si coincide con un deporte habitual salvo
    tildes o mayúsculas ('futbol americano'), devuelve el nombre de la lista,
    para no acabar con el mismo deporte escrito de varias formas."""
    texto = " ".join(texto.split())
    for habitual in DEPORTES_HABITUALES:
        if _sin_acentos(habitual) == _sin_acentos(texto):
            return habitual
    return texto

def _init_state():
    if "patas_temp" not in st.session_state:
        st.session_state.patas_temp = [
            {"casa_apuestas": "", "seleccion": "", "cuota": 1.01},
            {"casa_apuestas": "", "seleccion": "", "cuota": 1.01},
        ]
    st.session_state.setdefault("form_version", 0)


def _clave(nombre):
    """Clave de un widget del formulario, con la versión actual incluida.

    Streamlit no reinicia un widget a su valor por defecto solo con borrar su
    entrada de session_state y volver a ejecutar el script (el navegador
    conserva lo último que mostró para esa misma key); hace falta darle una
    key distinta. Por eso, al guardar una surebet subimos `form_version`: con
    eso cambian TODAS las keys del formulario a la vez y cada widget nace de
    cero, vacío, en la siguiente ejecución."""
    return f"{nombre}_v{st.session_state.form_version}"


def _limpiar_selecciones_patas():
    """Borra los valores de selección de cada pata (que dependen del mercado
    elegido) para que no quede guardado uno que ya no es válido si el
    desplegable cambia de opciones."""
    for i in range(len(st.session_state.patas_temp)):
        for prefijo in _PREFIJOS_SELECCION_PATA:
            st.session_state.pop(_clave(f"{prefijo}{i}"), None)


def _casas_en_negativo(casas):
    """De las casas indicadas, las que tienen el líquido en negativo, con lo
    que les falta para volver a cero."""
    return {
        c["casa_apuestas"]: round(-c["liquido"], 2)
        for c in db.listar_bankroll()
        if c["casa_apuestas"] in casas and c["liquido"] < -0.005
    }


def _descartar_deposito():
    st.session_state.pop("depositos_pendientes", None)


@st.dialog("💰 Falta líquido", on_dismiss=_descartar_deposito)
def _dialogo_deposito(faltantes):
    """Ventana que salta al guardar una surebet que deja en negativo el
    líquido de alguna casa, para registrar el depósito hecho para cubrirla.
    Viene rellena con la casa, lo que falta y la fecha de hoy, pero todo se
    puede cambiar."""
    st.write("Con esta apuesta el líquido ha quedado en negativo en:")
    for casa, falta in faltantes.items():
        st.markdown(f"- **{casa}**: {-falta:,.2f} €")
    st.caption("Registra el depósito que has hecho para cubrirla. Puedes cambiar la casa, el importe y la fecha.")

    nombres = [c["casa_apuestas"] for c in db.listar_bankroll()]
    primera = next(iter(faltantes))
    # Las keys llevan la casa con la que se abre la ventana: si vuelve a salir
    # para la siguiente casa en negativo, los campos nacen de cero con ella
    # en vez de conservar lo elegido para la anterior.
    casa = st.selectbox(
        "Casa", options=nombres, index=nombres.index(primera), key=f"deposito_dialogo_casa_{primera}"
    )
    importe = st.number_input(
        "Importe (€)", min_value=0.01, step=1.0, format="%.2f",
        value=max(faltantes.get(casa, 0.0), 0.01), key=f"deposito_dialogo_importe_{primera}_{casa}",
    )
    fecha = st.date_input("Fecha", value=date.today(), key=f"deposito_dialogo_fecha_{primera}")

    col_si, col_no = st.columns(2)
    if col_si.button("Registrar depósito", type="primary", use_container_width=True):
        db.registrar_movimiento_bankroll(casa, "deposito", importe, fecha.isoformat())
        # Si había más de una casa en negativo, la ventana vuelve a salir
        # con la siguiente.
        restantes = _casas_en_negativo(faltantes.keys())
        if restantes:
            st.session_state["depositos_pendientes"] = restantes
        else:
            _descartar_deposito()
        st.rerun()
    if col_no.button("Ahora no", use_container_width=True):
        _descartar_deposito()
        st.rerun()


def _formulario_nueva_surebet():
    st.subheader("Nueva surebet")

    col_a, col_b = st.columns(2)
    with col_a:
        fecha = st.date_input("Fecha de la apuesta", value=date.today(), key=_clave("fecha_nueva_surebet"))
        col_fecha_ev, col_hora_ev = st.columns(2)
        fecha_evento = col_fecha_ev.date_input(
            "Fecha del evento", value=date.today(), key=_clave("fecha_evento_nueva_surebet")
        )
        # Sin valor por defecto: obliga a escribir la hora real del partido en
        # vez de guardar sin darse cuenta una hora inventada.
        hora_evento = col_hora_ev.time_input(
            "Hora del evento", value=None, step=300, key=_clave("hora_evento_nueva_surebet")
        )
        deporte = st.selectbox(
            "Deporte",
            options=[""] + DEPORTES_HABITUALES + ["Otro..."],
            index=0,
            key=_clave("deporte_select"),
        )
        if deporte == "Otro...":
            deporte = _normalizar_deporte(st.text_input("Nombre del deporte", key=_clave("deporte_otro")))
        evento = st.text_input(
            "Evento", placeholder="Ej. Real Madrid vs Barcelona", key=_clave("evento_nueva_surebet")
        )
    with col_b:
        # Si el deporte acaba de cambiar, el mercado elegido para el deporte
        # anterior puede no tener sentido (o no existir siquiera) en la nueva
        # lista: se limpia para forzar a elegir uno válido en vez de arrastrar
        # uno inválido que rompería el desplegable.
        if st.session_state.get("_deporte_anterior") != deporte:
            st.session_state.pop(_clave("mercado_select"), None)
            st.session_state.pop(_clave("mercado_otro"), None)
            _limpiar_selecciones_patas()
            st.session_state["_deporte_anterior"] = deporte

        mercados_disponibles = MERCADOS_POR_DEPORTE.get(deporte, MERCADOS_HABITUALES)
        mercado = st.selectbox(
            "Mercado",
            options=[""] + mercados_disponibles + ["Otro..."],
            index=0,
            key=_clave("mercado_select"),
        )
        if mercado == "Otro...":
            mercado = " ".join(st.text_input("Nombre del mercado", key=_clave("mercado_otro")).split())

        # Igual que con el deporte: si el mercado cambia, las selecciones ya
        # elegidas en cada pata (ligadas a las opciones del mercado anterior)
        # dejan de ser válidas.
        if st.session_state.get("_mercado_anterior") != mercado:
            _limpiar_selecciones_patas()
            st.session_state["_mercado_anterior"] = mercado

        notas = st.text_input(
            "Notas (opcional)", placeholder="Cualquier detalle relevante", key=_clave("notas_nueva_surebet")
        )

    st.markdown("**Patas de la surebet** (una fila por casa de apuestas)")

    col_btn1, col_btn2, _ = st.columns([1, 1, 3])
    with col_btn1:
        if st.button("➕ Añadir pata"):
            st.session_state.patas_temp.append({"casa_apuestas": "", "seleccion": "", "cuota": 1.01})
    with col_btn2:
        if st.button("➖ Quitar última pata") and len(st.session_state.patas_temp) > 2:
            st.session_state.patas_temp.pop()

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
        st.session_state.get(_clave(f"cuota_{i}"), p.get("cuota", 1.01))
        for i, p in enumerate(st.session_state.patas_temp)
    ]
    selecciones = [p.get("seleccion", "") for p in st.session_state.patas_temp]
    importes_actuales = [
        st.session_state.get(_clave(f"importe_{i}"), p.get("importe", 0.0)) or 0.0
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
                st.session_state[_clave(f"importe_{i}")] = round(importe, 2)
        st.rerun()

    st.markdown("**Patas de la surebet** (una fila por casa de apuestas)")

    casas_conocidas = db.listar_nombres_casas()
    liquido_por_casa = {c["casa_apuestas"]: c["liquido"] for c in db.listar_bankroll()}

    for i, pata in enumerate(st.session_state.patas_temp):
        with st.container(border=True):
            st.caption(f"Pata #{i + 1}")
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1.3])
            with c1:
                pata["casa_apuestas"] = st.selectbox(
                    f"Casa de apuestas #{i + 1}",
                    options=[""] + casas_conocidas + ["Otra..."],
                    index=0,
                    key=_clave(f"casa_{i}"),
                )
                if pata["casa_apuestas"] == "Otra...":
                    pata["casa_apuestas"] = st.text_input(
                        "Nombre de la casa", key=_clave(f"casa_otra_{i}")
                    ).strip()
                if pata["casa_apuestas"] in liquido_por_casa:
                    st.caption(f"Líquido disponible: {liquido_por_casa[pata['casa_apuestas']]:,.2f} €")
            with c2:
                if mercado == MERCADO_CON_LINEA:
                    sub1, sub2 = st.columns([1, 1])
                    tipo_linea = sub1.selectbox(
                        f"Tipo #{i + 1}", options=["Más de", "Menos de"], key=_clave(f"seleccion_tipo_{i}")
                    )
                    linea = sub2.number_input(
                        f"Línea #{i + 1}", min_value=0.0, step=0.5, format="%.2f",
                        key=_clave(f"seleccion_linea_{i}"),
                    )
                    pata["seleccion"] = f"{tipo_linea} {linea:g}"
                elif mercado == MERCADO_CON_HANDICAP:
                    sub1, sub2 = st.columns([1, 1])
                    lado = sub1.selectbox(
                        f"Lado #{i + 1}", options=_lados(deporte, mercado),
                        key=_clave(f"seleccion_lado_{i}"),
                    )
                    linea = sub2.number_input(
                        f"Hándicap #{i + 1}", step=0.25, format="%.2f", key=_clave(f"seleccion_handicap_{i}")
                    )
                    pata["seleccion"] = f"{lado} {linea:+g}"
                elif _selecciones_cerradas(deporte, mercado):
                    opciones = _selecciones_cerradas(deporte, mercado) + ["Otra..."]
                    seleccionada = st.selectbox(
                        f"Selección #{i + 1}", options=opciones, key=_clave(f"seleccion_select_{i}")
                    )
                    if seleccionada == "Otra...":
                        pata["seleccion"] = st.text_input(
                            f"Selección #{i + 1} (personalizada)", key=_clave(f"seleccion_otra_{i}")
                        )
                    else:
                        pata["seleccion"] = seleccionada
                else:
                    pata["seleccion"] = st.text_input(
                        f"Selección #{i + 1}", placeholder="Ej. Local, Más de 2.5...",
                        key=_clave(f"seleccion_{i}"),
                    )
            with c3:
                pata["cuota"] = st.number_input(
                    f"Cuota #{i + 1}", min_value=1.01, step=0.01, format="%.2f", key=_clave(f"cuota_{i}")
                )
            with c4:
                pata["importe"] = st.number_input(
                    f"Importe (€) #{i + 1}", min_value=0.0, step=1.0, format="%.2f", key=_clave(f"importe_{i}")
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
                key=_clave("confirmar_riesgo"),
            )
    else:
        beneficios = None
        peor_beneficio = 0.0
        st.info("Escribe el importe a apostar en cada pata para ver el resultado esperado.")

    if st.button("💾 Guardar surebet", type="primary", disabled=not confirmar_riesgo or importe_total <= 0):
        patas_guardar = [
            {
                "casa_apuestas": p["casa_apuestas"].strip(),
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
        elif not evento or not mercado or not deporte:
            st.error("Deporte, evento y mercado son obligatorios.")
        elif hora_evento is None:
            st.error("Indica la hora del evento.")
        else:
            db.crear_surebet(
                fecha=fecha.isoformat(),
                fecha_evento=datetime.combine(fecha_evento, hora_evento).strftime("%Y-%m-%d %H:%M"),
                evento=evento,
                deporte=deporte,
                mercado=mercado,
                importe_total=importe_total,
                beneficio_pct=(peor_beneficio / importe_total * 100) if importe_total else 0.0,
                beneficio_importe=peor_beneficio,
                notas=notas,
                patas=patas_guardar,
            )
            # El importe de cada pata ha pasado de líquido a 'en juego': si
            # alguna casa se ha quedado en negativo, se ofrece registrar el
            # depósito nada más volver a dibujar la página.
            faltantes = _casas_en_negativo({p["casa_apuestas"] for p in patas_guardar})
            if faltantes:
                st.session_state["depositos_pendientes"] = faltantes
            st.session_state.form_version += 1
            st.session_state.patas_temp = [
                {"casa_apuestas": "", "seleccion": "", "cuota": 1.01},
                {"casa_apuestas": "", "seleccion": "", "cuota": 1.01},
            ]
            st.session_state.pop("_deporte_anterior", None)
            st.session_state.pop("_mercado_anterior", None)
            st.success("Surebet guardada correctamente.")
            st.rerun()


def render():
    _init_state()
    # La ventana sigue saliendo mientras quede alguna casa en negativo por la
    # última apuesta guardada, hasta registrar el depósito, pulsar "Ahora no"
    # o cerrarla (con la X, Esc o haciendo clic fuera: on_dismiss).
    faltantes = st.session_state.get("depositos_pendientes")
    if faltantes:
        _dialogo_deposito(faltantes)
    _formulario_nueva_surebet()
