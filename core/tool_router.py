def detect_intent(user_input: str):

    text = user_input.lower().strip()

    # =========================
    # MEMORY INTENT
    # =========================
    if text.startswith("nama saya"):
        return "memory"

    if "siapa nama saya" in text:
        return "memory"

    # =========================
    # MATH INTENT
    # =========================
    math_symbols = ["+", "-", "*", "/"]

    if any(symbol in text for symbol in math_symbols):
        return "math"

    # =========================
    # SEARCH INTENT
    # =========================
    search_keywords = [
        "berita",
        "terbaru",
        "presiden",
        "menteri",
        "gubernur",
        "harga",
        "berapa harga",
        "tahun",
        "hari ini",
        "siapa",
        "kapan",
        "dimana",
        "di mana"
    ]

    if any(word in text for word in search_keywords):
        return "search"

    # =========================
    # DEFAULT CHAT
    # =========================
    return "chat"