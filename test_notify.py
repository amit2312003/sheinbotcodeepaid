import asyncio
from aiogram import Bot

BOT_TOKEN = "8475505416:AAEFss33GOvV89DF0TrwqYjq_RnfP72VSuM"
ADMIN_ID = 1455619072

async def main():
    bot = Bot(token=BOT_TOKEN)
    try:
        await bot.send_message(ADMIN_ID, "Test admin notification!")
        print("✅ Message sent to admin account.")
    except Exception as e:
        print("❌ Failed to send message to admin:", e)
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
