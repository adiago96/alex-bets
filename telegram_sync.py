# telegram_sync.py
"""Sincronización bajo demanda de oportunidades desde el canal de Telegram.

A diferencia de telegram_listener.py (un proceso que tiene que quedarse
escuchando en tiempo real, y por tanto encendido 24/7), esto se conecta a
Telegram, repasa el historial reciente del canal, guarda lo que encuentre y
se desconecta. Se piensa para llamarse cada vez que alguien abre la pestaña
"Oportunidades" de la app (ver paginas/oportunidades.py), desde cualquier
dispositivo, sin depender de que un ordenador concreto esté encendido: como
Telegram guarda el historial del canal, no se pierde nada por mucho tiempo
que pase entre una consulta y la siguiente.

Requiere en .streamlit/secrets.toml la sección [telegram] con api_id,
api_hash, canal y session (esta última se genera una vez con
generar_sesion_telegram.py). Ver .streamlit/secrets.example.toml.
"""

import asyncio
import os
from datetime import datetime, timedelta

from telethon import TelegramClient
from telethon.sessions import StringSession

import database as db
from telegram_parser import calcular_duracion, parsear_mensaje_sure

DIAS_HISTORIAL = 2  # cuántos días hacia atrás repasa en cada sincronización


def _credenciales_telegram():
    cfg = {}
    try:
        import streamlit as st
        cfg = dict(st.secrets.get("telegram", {}))
    except Exception:
        pass

    api_id = cfg.get("api_id") or os.environ.get("TELEGRAM_API_ID")
    api_hash = cfg.get("api_hash") or os.environ.get("TELEGRAM_API_HASH")
    canal = cfg.get("canal") or os.environ.get("TELEGRAM_CANAL")
    session = cfg.get("session") or os.environ.get("TELEGRAM_SESSION")

    if not all([api_id, api_hash, canal, session]):
        raise RuntimeError(
            "Faltan credenciales de Telegram. Rellena la sección [telegram] en "
            ".streamlit/secrets.toml (api_id, api_hash, canal, session) — ver "
            ".streamlit/secrets.example.toml. La 'session' se genera una vez con "
            "generar_sesion_telegram.py."
        )
    return int(api_id), api_hash, canal, session


def _hora_local(fecha_utc):
    """Convierte la fecha (con zona horaria UTC) de un mensaje de Telegram a
    hora local sin zona horaria, para poder compararla con datetime.now()."""
    return fecha_utc.astimezone().replace(tzinfo=None)


def _procesar_mensaje(texto, fecha_mensaje, firmas_vistas):
    """Interpreta un mensaje y lo guarda si es una oportunidad vigente
    (todavía no ha empezado). Devuelve True si se ha guardado/actualizado."""
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
    return True


async def _sincronizar_async():
    api_id, api_hash, canal, session = _credenciales_telegram()
    limite = datetime.now().astimezone() - timedelta(days=DIAS_HISTORIAL)
    firmas_vistas = set()
    guardadas = 0

    client = TelegramClient(StringSession(session), api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError(
                "La sesión de Telegram guardada ya no es válida. Genera una nueva "
                "con: python generar_sesion_telegram.py"
            )
        async for mensaje in client.iter_messages(canal):
            if mensaje.date < limite:
                break
            if _procesar_mensaje(mensaje.text, mensaje.date, firmas_vistas):
                guardadas += 1
    finally:
        await client.disconnect()

    db.eliminar_oportunidades_caducadas()
    return guardadas


def sincronizar(forzar=False, cooldown_segundos=60):
    """Trae oportunidades nuevas/actualizadas del canal de Telegram.

    Si `forzar` es False (uso normal al abrir la pestaña), solo sincroniza si
    ha pasado `cooldown_segundos` desde la última vez (para no conectar a
    Telegram en cada rerun de Streamlit ni desde varios dispositivos a la
    vez). Devuelve el número de oportunidades guardadas/actualizadas, o None
    si no tocaba sincronizar todavía.
    """
    if not forzar and not db.debe_sincronizar_oportunidades(cooldown_segundos):
        return None
    return asyncio.run(_sincronizar_async())
