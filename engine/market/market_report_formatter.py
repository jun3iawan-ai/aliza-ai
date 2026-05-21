def format_market_report(data):

    symbol = data.get("symbol", "UNKNOWN")

    def _fmt(value):
        """Format nilai agar tidak pernah menampilkan None."""
        if value is None:
            return "DATA TIDAK TERSEDIA"
        return value

    price = data.get("price")
    trend = data.get("trend")
    cycle_phase = data.get("cycle_phase")
    market_phase_prediction = data.get("market_phase_prediction")
    bull_probability = data.get("bull_probability")
    whale_activity = data.get("whale_activity")
    stablecoin_flow = data.get("stablecoin_flow")
    funding_status = data.get("funding_status")
    open_interest_level = data.get("open_interest_level")
    liquidation_risk = data.get("liquidation_risk")
    market_risk_score = data.get("market_risk_score")

    # Khusus bull_probability, tambahkan '%' jika ada angka.
    if bull_probability is None:
        bull_text = "DATA TIDAK TERSEDIA"
    else:
        bull_text = f"{bull_probability}%"

    message = (
        f"📊 INTELIJEN MARKET {symbol}\n\n"
        f"Harga {symbol}: ${_fmt(price)}\n"
        f"Trend: {_fmt(trend)}\n\n"

        f"Siklus Market: {_fmt(cycle_phase)}\n"
        f"Prediksi AI: {_fmt(market_phase_prediction)}\n\n"

        f"Probabilitas Bull Market: {bull_text}\n\n"

        f"Aktivitas Whale: {_fmt(whale_activity)}\n"
        f"Arus Stablecoin: {_fmt(stablecoin_flow)}\n\n"

        f"Funding Rate: {_fmt(funding_status)}\n\n"

        f"Open Interest: {_fmt(open_interest_level)}\n"
        f"Risiko Likuidasi: {_fmt(liquidation_risk)}\n\n"

        f"Tingkat Risiko Market: {_fmt(market_risk_score)}"
    )

    return message