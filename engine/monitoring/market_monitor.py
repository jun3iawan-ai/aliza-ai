import time
import requests

from engine.market.market_analyzer import btc_signal


TELEGRAM_BOT_TOKEN = "ISI_TOKEN_BOT_KAMU"
TELEGRAM_CHAT_ID = "ISI_CHAT_ID_KAMU"


def send_telegram(message):

    url = f"https://api.telegram.org/bot{8786090646:AAHemMG4wubdS7bj_l-VGwKGjCelclk_3iU}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass


def format_message(data):

    return f"""
ALIZA MARKET ALERT

BTC Price: ${data['price']}

RSI: {data['rsi']}
Fear & Greed: {data['fear_greed']}
BTC Dominance: {data['dominance']}%

Trend: {data['trend']}
Market Score: {data['market_score']}

Signal: {data['signal']}

Analysis:
{data['analysis']}
"""


def monitor_market():

    last_signal = None

    while True:

        try:

            data = btc_signal()

            signal = data.get("signal")

            if signal != last_signal:

                msg = format_message(data)

                send_telegram(msg)

                last_signal = signal

                print("Alert sent:", signal)

        except Exception as e:

            print("monitor error:", e)

        time.sleep(300)