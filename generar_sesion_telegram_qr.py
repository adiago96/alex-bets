# generar_sesion_telegram_qr.py
"""Genera la sesión de Telegram (StringSession) por código QR, como
alternativa a generar_sesion_telegram.py para cuando el código de
verificación por SMS/app no llega. Escaneas un QR desde el móvil, sin
necesidad de escribir ningún código.

Ejecútalo UNA VEZ:

    .\\venv\\Scripts\\python.exe generar_sesion_telegram_qr.py

Genera una imagen telegram_qr.png en esta misma carpeta: ábrela y, desde el
móvil, ve a Telegram > Ajustes > Dispositivos > Vincular dispositivo de
escritorio, y escanéala. Al terminar imprime una línea session = "..." —
cópiala en .streamlit/secrets.toml, dentro de la sección [telegram].

Requiere el paquete 'qrcode' además de telethon:
    .\\venv\\Scripts\\python.exe -m pip install "qrcode[pil]"

Necesita que api_id y api_hash ya estén en .streamlit/secrets.toml (sección
[telegram]) o en las variables de entorno TELEGRAM_API_ID / TELEGRAM_API_HASH.
"""

import asyncio
import os

from telethon import TelegramClient
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
    import qrcode

    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.connect()

    qr_login = await client.qr_login()
    qrcode.make(qr_login.url).save("telegram_qr.png")
    print("\nQR generado en telegram_qr.png. Ábrelo y, desde el móvil:")
    print("Telegram > Ajustes > Dispositivos > Vincular dispositivo de escritorio > escanéalo.\n")
    print("Esperando a que lo escanees...")

    await qr_login.wait()

    print("\n✅ Sesión generada. Copia esta línea en .streamlit/secrets.toml, dentro de [telegram]:\n")
    print(f'session = "{client.session.save()}"\n')

    await client.disconnect()


asyncio.run(main())
