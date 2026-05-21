import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.market.market_analyzer import btc_signal
from engine.market.market_snapshot_engine import get_market_snapshot, is_snapshot_valid
import engine.market.market_snapshot_engine as snapshot_state
from engine.signal_engine import SIGNAL_TYPE_INFORMATIONAL, process_signal

load_dotenv()

IS_PRIMARY_DISPATCHER = os.getenv("IS_PRIMARY_DISPATCHER", "true").strip().lower() == "true"
SNAPSHOT_MAX_AGE_SEC = int(os.getenv("SNAPSHOT_MAX_AGE_SEC", "300"))

logging.basicConfig(level=logging.INFO)

LAST_SIGNAL = None


async def send_alert_via_primary_dispatcher(message: str, data: dict, signal_key: str) -> None:
    """
    Alert melalui unified gateway (process_signal).
    """
    tsu = data.get("trade_setup") or {}
    sig = {
        "symbol": "BTCUSDT",
        "type": str(signal_key),
        "entry": data.get("price"),
        "stop_loss": tsu.get("sl"),
        "take_profit": tsu.get("tp1"),
        "source": "btc_alert",
        "coin": "BTC",
        "setup": str(signal_key),
        "signal_type": SIGNAL_TYPE_INFORMATIONAL,
    }
    key = f"market_bot|{signal_key}"
    await process_signal(key, sig, message, chat_id=None)


async def market_loop():

    global LAST_SIGNAL

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
            crash = data.get("crash_alert")

            message = None

            if crash == "HIGH":

                message = (
                    "🚨 ALIZA CRASH ALERT\n\n"
                    f"Crash Probability: {data.get('crash_probability')}%\n\n"
                    "Recommendation:\n"
                    "WAIT / REDUCE POSITION"
                )
                sk = "CRASH"

            elif signal in ["BUY", "SELL"]:

                message = (
                    "📡 ALIZA MARKET SIGNAL\n\n"
                    f"Signal: {signal}\n"
                    f"Trend: {data.get('trend')}\n"
                    f"Price: ${data.get('price')}"
                )
                sk = str(signal)
            else:
                message = None
                sk = ""

            if message and message != LAST_SIGNAL:

                LAST_SIGNAL = message

                await send_alert_via_primary_dispatcher(message, data, sk)

        except Exception as e:

            logging.error(f"Market bot error: {e}")

        await asyncio.sleep(300)


async def main():

    logging.info("Aliza Market Bot started")

    await market_loop()


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())