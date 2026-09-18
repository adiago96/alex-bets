# telegram_debug.py
"""Script de diagnóstico: muestra el texto exacto (repr, para ver caracteres
raros) de los últimos mensajes del canal configurado, para comparar con el
formato que espera telegram_parser.py. Bórralo cuando ya no lo necesites."""

import asyncio

from telethon import TelegramClient

from telegram_config import API_HASH, API_ID, CANAL

client = TelegramClient("alex_bets_session", API_ID, API_HASH)


async def main():
    await client.connect()

    entidad = await client.get_entity(CANAL)
    nombre = getattr(entidad, "title", None) or getattr(entidad, "username", None) or str(entidad)
    print(f"Canal resuelto: {nombre}\n")

    async for mensaje in client.iter_messages(CANAL, limit=5):
        print("=" * 60)
        print(f"fecha: {mensaje.date}")
        print(f"texto (repr): {mensaje.text!r}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
