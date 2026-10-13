from engine.market_signal import generate_signal
from engine.market.market_universe import MAJOR_COINS, get_analyzable_coins
import logging


def update_market_cache():

    updated = 0

    for coin in get_analyzable_coins(MAJOR_COINS):

        try:

            generate_signal(coin)
            updated += 1

        except Exception as e:

            logging.error(f"CACHE UPDATE ERROR {coin}: {e}")

    logging.info(f"Market cache updated for {updated} coins")

    return updated