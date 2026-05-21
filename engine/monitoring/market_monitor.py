import os
import logging
import asyncio
from dotenv import load_dotenv

from engine.market.market_analyzer import btc_signal
from engine.market.market_snapshot_engine import get_market_snapshot, is_snapshot_valid
import engine.market.market_snapshot_engine as snapshot_state
from engine.signal_engine import SIGNAL_TYPE_INFORMATIONAL, process_signal

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
IS_PRIMARY_DISPATCHER = os.getenv("IS_PRIMARY_DISPATCHER", "true").strip().lower() == "true"
SNAPSHOT_MAX_AGE_SEC = int(os.getenv("SNAPSHOT_MAX_AGE_SEC", "300"))

logging.basicConfig(level=logging.INFO)


def format_message(data):

    return f"""
ALIZA MARKET ALERT

BTC Price: ${data.get('price')}

RSI: {data.get('rsi')}
Fear & Greed: {data.get('fear_greed')}
BTC Dominance: {data.get('dominance')}%

Trend: {data.get('trend')}
Market Score: {data.get('market_score', '—')}

Signal: {data.get('signal')}

Analysis:
{data.get('analysis', '—')}
"""


async def monitor_market():
    if not TELEGRAM_BOT_TOKEN:
        logging.error("TELEGRAM_BOT_TOKEN not set. Stopping market monitor service.")
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    if not TELEGRAM_CHAT_ID:
        logging.error("TELEGRAM_CHAT_ID not set. Stopping market monitor service.")
        raise RuntimeError("TELEGRAM_CHAT_ID not set")

    last_signal = None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    while True:

        try:
            if snapshot_state.CIRCUIT_BREAKER_ACTIVE:
                logging.critical("SYSTEM HALTED: CIRCUIT BREAKER ACTIVE")
                await asyncio.sleep(300)
                continue
            snapshot = get_market_snapshot()
            if not is_snapshot_valid(snapshot, SNAPSHOT_MAX_AGE_SEC):
                logging.warning("GLOBAL GUARD: SNAPSHOT INVALID — ABORTING PROCESS")
                await asyncio.sleep(300)
                continue

            data = btc_signal()
            if data is None:
                await asyncio.sleep(300)
                continue

            signal = data.get("signal")

            if signal != last_signal:

                msg = format_message(data)
                tsu = data.get("trade_setup") or {}
                uni = {
                    "symbol": "BTCUSDT",
                    "type": str(signal),
                    "entry": data.get("price"),
                    "stop_loss": tsu.get("sl"),
                    "take_profit": tsu.get("tp1"),
                    "confidence": data.get("confidence"),
                    "source": "btc_alert",
                    "coin": "BTC",
                    "setup": "MARKET_MONITOR",
                    "signal_type": SIGNAL_TYPE_INFORMATIONAL,
                }
                key = f"monitor|BTC|{signal}"

                async def _send():
                    await process_signal(key, uni, msg, chat_id=TELEGRAM_CHAT_ID)

                try:
                    loop.create_task(_send())
                except Exception as dispatch_err:
                    logging.error("dispatcher error: %s", dispatch_err)

                last_signal = signal

                logging.info("Alert sent: %s", signal)

        except Exception as e:

            logging.error("monitor error: %s", e)

        await asyncio.sleep(300)


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(monitor_market())


if __name__ == "__main__":
    main()