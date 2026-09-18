# telegram_listener.py
"""Escucha el canal de Telegram y guarda las oportunidades ('sures') que
detecta en la base de datos de Alex Bets, para poder verlas y usarlas desde
la app de Streamlit.

Al arrancar, primero recupera los mensajes de los últimos DIAS_HISTORIAL días
(por si el ordenador ha estado apagado y se han perdido mensajes), y luego se
queda escuchando los nuevos que vayan llegando.

Se ejecuta como proceso independiente, en una terminal aparte:

    python telegram_listener.py

Requiere:
1. Tener telethon instalado (ver requirements.txt).
2. Un fichero telegram_config.py con tus credenciales (copia
   telegram_config.example.py y rellénalo, ver ese fichero para más detalle).

La primera vez que se ejecuta te pedirá el número de teléfono y el código de
verificación por consola (login normal de Telegram). Después reutiliza la
sesión guardada en alex_bets_session.session y no vuelve a pedir nada.
"""

import asyncio
from datetime import datetime, timedelta

from telethon import TelegramClient, events

import database as db
from telegram_config import API_HASH, API_ID, CANAL
from telegram_parser import calcular_duracion, parsear_mensaje_sure

DIAS_HISTORIAL = 3  # cuántos días hacia atrás recupera al arrancar

client = TelegramClient("alex_bets_session", API_ID, API_HASH)


def _hora_local(fecha_utc):
    """Convierte la fecha (con zona horaria UTC) de un mensaje de Telegram a
    hora local sin zona horaria, para poder compararla con datetime.now()."""
    return fecha_utc.astimezone().replace(tzinfo=None)


def _procesar_mensaje(texto, fecha_mensaje, firmas_vistas=None):
    """Interpreta un mensaje y lo guarda si es una oportunidad vigente
    (todavía no ha empezado). Devuelve True si se ha guardado.

    `firmas_vistas`, si se pasa, evita que al recorrer el historial una
    versión más antigua del mismo partido sobrescriba la más reciente que ya
    se guardó (el historial se recorre del más nuevo al más viejo)."""
    oportunidad = parsear_mensaje_sure(texto or "")
    if oportunidad is None:
        return False

    duracion = calcular_duracion(oportunidad.comienza_en)
    if duracion is None:
        return False

    empieza_en = _hora_local(fecha_mensaje) + duracion
    if empieza_en <= datetime.now():
        return False  # el evento ya habrá empezado, no tiene sentido guardarlo

    patas = [
        {"casa_apuestas": p.casa_apuestas, "seleccion": p.seleccion, "cuota": p.cuota}
        for p in oportunidad.patas
    ]

    if firmas_vistas is not None:
        firma = db.firma_oportunidad(oportunidad.evento, patas)
        if firma in firmas_vistas:
            return False
        firmas_vistas.add(firma)

    db.guardar_oportunidad(
        roi_pct=oportunidad.roi_pct,
        torneo=oportunidad.torneo,
        evento=oportunidad.evento,
        comienza_en=oportunidad.comienza_en,
        empieza_en=empieza_en.strftime("%Y-%m-%d %H:%M:%S"),
        texto_original=oportunidad.texto_original,
        patas=patas,
    )
    print(f"Oportunidad guardada: {oportunidad.evento} (ROI {oportunidad.roi_pct}%, empieza {empieza_en.strftime('%d/%m %H:%M')})")
    return True


async def _rellenar_historial():
    limite = datetime.now().astimezone() - timedelta(days=DIAS_HISTORIAL)
    firmas_vistas = set()
    total_mensajes = 0
    total_sures = 0
    guardadas = 0
    async for mensaje in client.iter_messages(CANAL):
        if mensaje.date < limite:
            break
        total_mensajes += 1
        if mensaje.text and "SURE SPAIN" in mensaje.text:
            total_sures += 1
        if _procesar_mensaje(mensaje.text, mensaje.date, firmas_vistas):
            guardadas += 1
    print(
        f"Historial revisado: {total_mensajes} mensajes de los últimos {DIAS_HISTORIAL} días, "
        f"{total_sures} eran oportunidades del canal, {guardadas} seguían vigentes (no habían empezado)."
    )


@client.on(events.NewMessage(chats=CANAL))
async def _al_recibir_mensaje(event):
    db.eliminar_oportunidades_caducadas()
    _procesar_mensaje(event.message.text, event.message.date)


async def _main():
    db.init_db()
    db.eliminar_oportunidades_caducadas()
    await client.start()
    print("Recuperando historial reciente del canal...")
    await _rellenar_historial()
    print(f"Escuchando el canal: {CANAL}")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(_main())
