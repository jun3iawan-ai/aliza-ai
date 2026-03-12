from engine.utils.market_cache import get_all_market_data


# =========================
# SCAN OPPORTUNITIES
# =========================

def scan_opportunities():

    market_data = get_all_market_data()

    if not market_data:
        return []

    opportunities = []

    for coin, data in market_data.items():

        if not data:
            continue

        trade = data.get("trade_setup")

        if not trade:
            continue

        rr = trade.get("risk_reward")

        if rr is None:
            continue

        # filter minimum RR
        if rr < 1.3:
            continue

        opportunities.append({
            "coin": coin,
            "setup": trade.get("setup"),
            "entry": trade.get("entry"),
            "sl": trade.get("sl"),
            "tp1": trade.get("tp1"),
            "tp2": trade.get("tp2"),
            "rr": rr,
            "trend": data.get("trend"),
            "confidence": trade.get("confidence"),
            "risk_quality": trade.get("risk_quality"),
        })

    opportunities.sort(key=lambda x: x["rr"], reverse=True)

    return opportunities


# =========================
# OPPORTUNITY REPORT
# =========================

def opportunity_report():

    opportunities = scan_opportunities()

    if not opportunities:
        return "Tidak ada peluang trading saat ini."

    top = opportunities[:3]

    message = "🎯 TOP TRADING OPPORTUNITY\n\n"

    separator = "\n━━━━━━━━━━━━━━\n\n"

    for i, opp in enumerate(top, start=1):

        coin = opp.get("coin", "")
        setup = opp.get("setup", "")
        entry = opp.get("entry")
        sl = opp.get("sl")
        tp1 = opp.get("tp1")
        tp2 = opp.get("tp2")
        rr = round(opp.get("rr", 0), 2)
        trend = opp.get("trend") or "—"
        confidence = opp.get("confidence")
        risk_quality = opp.get("risk_quality") or "—"

        message += f"{i}️⃣ {coin} {setup}\n"
        message += f"Trend : {trend}\n"

        if entry is not None:
            message += f"Entry : {round(entry, 2)}\n"
        if sl is not None:
            message += f"SL : {round(sl, 2)}\n"
        if tp1 is not None:
            message += f"TP1 : {round(tp1, 2)}\n"
        if tp2 is not None:
            message += f"TP2 : {round(tp2, 2)}\n"

        message += f"RR : {rr}\n"
        if confidence is not None:
            message += f"Confidence : {confidence}\n"
        if risk_quality:
            message += f"Risk Quality : {risk_quality}\n"

        if i < len(top):
            message += separator

    return message