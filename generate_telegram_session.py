"""Generate a Telethon StringSession locally; never commit or share the output."""
import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

async def main():
    api_id = os.getenv("TELEGRAM_API_ID", "").strip() or input("Telegram API ID: ").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip() or input("Telegram API hash: ").strip()
    phone = input("Phone number with country code: ").strip()
    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.start(phone=phone)
    try:
        print("\nCopy this value directly into GitHub Actions secret TELEGRAM_SESSION_STRING.")
        print("Keep it private; it grants access to your Telegram account.\n")
        print(StringSession.save(client.session))
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
