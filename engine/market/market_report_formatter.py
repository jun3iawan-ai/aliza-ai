def format_market_report(data):

    symbol = data.get("symbol")

    message = (
        f"📊 INTELIJEN MARKET {symbol}\n\n"
        f"Harga {symbol}: ${data.get('price')}\n"
        f"Trend: {data.get('trend')}\n\n"

        f"Siklus Market: {data.get('cycle_phase')}\n"
        f"Prediksi AI: {data.get('market_phase_prediction')}\n\n"

        f"Probabilitas Bull Market: {data.get('bull_probability')}%\n\n"

        f"Aktivitas Whale: {data.get('whale_activity')}\n"
        f"Arus Stablecoin: {data.get('stablecoin_flow')}\n\n"

        f"Funding Rate: {data.get('funding_status')}\n\n"

        f"Open Interest: {data.get('open_interest_level')}\n"
        f"Risiko Likuidasi: {data.get('liquidation_risk')}\n\n"

        f"Tingkat Risiko Market: {data.get('market_risk_score')}"
    )

    return message