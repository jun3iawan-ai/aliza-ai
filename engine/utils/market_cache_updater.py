from engine.market.market_analyzer import market_signal
from engine.market.market_universe import MAJOR_COINS
import logging


def update_market_cache():

    updated = 0

    for coin in MAJOR_COINS:

        try:

            market_signal(coin)
            updated += 1

        except Exception as e:

            logging.error(f"CACHE UPDATE ERROR {coin}: {e}")

    logging.info(f"Market cache updated for {updated} coins")

    return updated