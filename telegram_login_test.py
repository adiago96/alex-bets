# telegram_login_test.py
"""Script de diagnóstico para el login de Telegram: fuerza el envío del
código por SMS y muestra qué tipo de envío ha hecho Telegram, para saber
por qué no llega. Bórralo cuando ya tengas el login funcionando
(telegram_listener.py hace el login normal solo)."""

import asyncio

from telethon import TelegramClient

from telegram_config import API_HASH, API_ID

client = TelegramClient("alex_bets_session", API_ID, API_HASH)


async def main():
    await client.connect()

    telefono = input("Teléfono (con +34...): ").strip()

    enviado = await client.send_code_request(telefono, force_sms=True)
    print(f"\nTipo de envío que ha usado Telegram: {type(enviado.type).__name__}")
    print(f"Detalle completo: {enviado}\n")

    codigo = input("Código recibido: ").strip()
    try:
        await client.sign_in(telefono, codigo, phone_code_hash=enviado.phone_code_hash)
        print("\n✅ Login correcto.")
    except Exception as e:
        print(f"\n❌ Error al iniciar sesión: {e}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
