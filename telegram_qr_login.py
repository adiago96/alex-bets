# telegram_qr_login.py
"""Login alternativo por código QR, para cuando el código por SMS/app no
llega. Genera una imagen QR (telegram_qr.png) que se escanea desde el móvil
en Telegram > Ajustes > Dispositivos > Vincular dispositivo de escritorio.

Requiere el paquete 'qrcode' además de telethon:
    pip install "qrcode[pil]"

Bórralo cuando ya tengas el login funcionando (telegram_listener.py hace el
login normal solo, reutilizando la sesión guardada)."""

import asyncio

import qrcode

from telethon import TelegramClient

from telegram_config import API_HASH, API_ID

client = TelegramClient("alex_bets_session", API_ID, API_HASH)


async def main():
    await client.connect()

    qr_login = await client.qr_login()
    qrcode.make(qr_login.url).save("telegram_qr.png")
    print("QR generado en telegram_qr.png.")
    print("En tu móvil: Telegram > Ajustes > Dispositivos > Vincular dispositivo de escritorio, y escanéalo.")
    print("Esperando a que lo escanees...")

    try:
        await qr_login.wait()
        print("\n✅ Login correcto. Ya puedes usar telegram_listener.py normalmente.")
    except Exception as e:
        print(f"\n❌ Error al iniciar sesión: {e}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
