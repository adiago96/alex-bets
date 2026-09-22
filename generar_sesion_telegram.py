# generar_sesion_telegram.py
"""Genera la cadena de sesión de Telegram (StringSession) que necesita
telegram_sync.py para funcionar en la nube, donde no hay consola para
escribir el código de verificación en cada arranque.

Ejecútalo UNA VEZ, en tu ordenador:

    .\\venv\\Scripts\\python.exe generar_sesion_telegram.py

Pide el número de teléfono y fuerza el envío del código por SMS (evita que
Telegram intente mandarlo a una sesión activa en otro dispositivo que ahora
mismo no esté conectado, que es la causa más habitual de que "no llegue" el
código). Al final imprime una cadena larga: cópiala en
.streamlit/secrets.toml, dentro de la sección [telegram], como session = "...".

Necesita que api_id y api_hash ya estén en .streamlit/secrets.toml (sección
[telegram]) o en las variables de entorno TELEGRAM_API_ID / TELEGRAM_API_HASH.
Consíguelos en https://my.telegram.org si todavía no los tienes.
"""

import asyncio
import os

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

try:
    import streamlit as st
    _cfg = dict(st.secrets.get("telegram", {}))
except Exception:
    _cfg = {}

api_id = _cfg.get("api_id") or os.environ.get("TELEGRAM_API_ID")
api_hash = _cfg.get("api_hash") or os.environ.get("TELEGRAM_API_HASH")

if not api_id or not api_hash:
    raise SystemExit(
        "Falta api_id/api_hash. Ponlos en .streamlit/secrets.toml (sección [telegram]) "
        "o en las variables de entorno TELEGRAM_API_ID / TELEGRAM_API_HASH antes de "
        "ejecutar este script."
    )


async def main():
    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.connect()

    telefono = input("Número de teléfono (con prefijo, ej. +34...): ").strip()
    enviado = await client.send_code_request(telefono, force_sms=True)
    print("Código solicitado por SMS (puede tardar uno o dos minutos en llegar).")
    codigo = input("Código recibido: ").strip()

    try:
        await client.sign_in(telefono, codigo, phone_code_hash=enviado.phone_code_hash)
    except SessionPasswordNeededError:
        contrasena = input("Tienes verificación en dos pasos activada, escribe tu contraseña: ")
        await client.sign_in(password=contrasena)

    print("\nSesión generada. Copia esta línea en .streamlit/secrets.toml, dentro de [telegram]:\n")
    print(f'session = "{client.session.save()}"\n')

    await client.disconnect()


asyncio.run(main())
