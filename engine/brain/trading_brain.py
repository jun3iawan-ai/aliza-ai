class TradingBrain:

    def analyze(self, market):

        price = market.get("price")
        rsi = market.get("rsi")
        trend = market.get("trend")
        fear = market.get("fear_greed")
        whale = market.get("whale_activity")

        support = market.get("support")
        resistance = market.get("resistance")

        if price is None or rsi is None or trend is None:
            return {"setup": "NO DATA"}

        setup = "NO SETUP"

        # =========================
        # SETUP DETECTION
        # RSI ekstrem (oversold) diperiksa dulu agar OVERSOLD BOUNCE
        # terdeteksi meskipun trend BEARISH.
        # =========================

        if rsi < 30:
            setup = "OVERSOLD BOUNCE"

        elif trend == "BULLISH" and rsi < 45:
            setup = "PULLBACK LONG"

        elif trend == "BEARISH" and rsi > 55:
            setup = "PULLBACK SHORT"

        elif trend == "BEARISH":
            setup = "SHORT CONTINUATION"

        entry = price

        # =========================
        # LONG TRADE LOGIC
        # =========================

        if "LONG" in setup or setup == "OVERSOLD BOUNCE":

            if support:
                sl = support * 0.99
            else:
                sl = price * 0.98

            if resistance:
                tp1 = resistance
                tp2 = resistance * 1.02
            else:
                tp1 = price * 1.03
                tp2 = price * 1.05

        # =========================
        # SHORT TRADE LOGIC
        # =========================

        else:

            if resistance:
                sl = resistance * 1.01
            else:
                sl = price * 1.02

            if support:
                tp1 = support
                tp2 = support * 0.98
            else:
                tp1 = price * 0.97
                tp2 = price * 0.95

        # =========================
        # RISK REWARD
        # =========================

        risk = abs(entry - sl)
        reward = abs(entry - tp2)

        rr = reward / risk if risk != 0 else 0

        # =========================
        # CONFIDENCE SCORE
        # =========================

        confidence = 0

        if trend == "BEARISH":
            confidence += 25

        if rsi and rsi < 50:
            confidence += 20

        if fear and fear < 25:
            confidence += 20

        if whale == "ACCUMULATING":
            confidence += 20

        if rr >= 2:
            confidence += 15

        confidence = min(confidence, 85)

        # =========================
        # RISK QUALITY
        # =========================

        if rr >= 3:
            risk_quality = "EXCELLENT"
        elif rr >= 2:
            risk_quality = "GOOD"
        elif rr >= 1:
            risk_quality = "MEDIUM"
        else:
            risk_quality = "POOR"

        # =========================
        # ROUND VALUES
        # =========================

        entry = round(entry, 2)
        sl = round(sl, 2)
        tp1 = round(tp1, 2)
        tp2 = round(tp2, 2)
        rr = round(rr, 2)

        return {
            "setup": setup,
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "risk_reward": rr,
            "confidence": confidence,
            "risk_quality": risk_quality
        }