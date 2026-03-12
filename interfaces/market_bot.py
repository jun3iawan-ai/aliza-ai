import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Bot

from engine.market.market_analyzer import btc_signal

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = 1490996477

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)

LAST_SIGNAL = None


async def market_loop():

    global LAST_SIGNAL

    while True:

        try:

            data = btc_signal()

            signal = data.get("signal")
            crash = data.get("crash_alert")

            message = None

            if crash == "HIGH":

                message = (
                    "🚨 ALIZA CRASH ALERT\n\n"
                    f"Crash Probability: {data.get('crash_probability')}%\n\n"
                    "Recommendation:\n"
                    "WAIT / REDUCE POSITION"
                )

            elif signal in ["BUY", "SELL"]:

                message = (
                    "📡 ALIZA MARKET SIGNAL\n\n"
                    f"Signal: {signal}\n"
                    f"Trend: {data.get('trend')}\n"
                    f"Price: ${data.get('price')}"
                )

            if message and message != LAST_SIGNAL:

                LAST_SIGNAL = message

                await bot.send_message(
                    chat_id=CHAT_ID,
                    text=message
                )

        except Exception as e:

            logging.error(f"Market bot error: {e}")

        await asyncio.sleep(300)


async def main():

    logging.info("Aliza Market Bot started")

    await market_loop()


if __name__ == "__main__":

    asyncio.run(main())