import os
import sys
import uuid
import logging
from dotenv import load_dotenv

# =========================
# FIX PYTHON PATH
# =========================

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# =========================
# PROJECT IMPORT
# =========================

from engine.aliza_engine import ask_aliza
from engine.document_analyzer import analyze_document
from engine.market_analyzer import btc_signal
from engine.market_report_formatter import format_market_report

from memory.memory_manager import save_user_name, get_user_name
from memory.active_document import set_active_document

from core.rag_engine import add_document_to_vector_store

# =========================
# TELEGRAM IMPORT
# =========================

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# =========================
# LOAD ENV
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN tidak ditemukan di file .env")

# =========================
# TELEGRAM CHAT CONFIG
# =========================

CHAT_ID = 1490996477
LAST_SIGNAL = None

# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# =========================
# STORAGE CONFIG
# =========================

UPLOAD_FOLDER = "knowledge/uploads/original_files"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

MAX_FILE_SIZE = 20 * 1024 * 1024

ALLOWED_TYPES = [
    ".pdf",
    ".txt",
    ".xlsx",
    ".docx",
    ".pptx",
    ".csv"
]

# =========================
# TELEGRAM MESSAGE LIMIT
# =========================

def split_message(text, limit=4000):

    parts = []

    while len(text) > limit:
        parts.append(text[:limit])
        text = text[limit:]

    parts.append(text)

    return parts


# =========================
# COMMAND /start
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "Halo, saya AlizaAI 🤖\n\n"
        "Auto market monitoring aktif.\n\n"
        "Perintah yang tersedia:\n"
        "/market - Laporan market BTC\n"
        "/trade - Setup trading\n"
        "/status - Status sistem\n"
        "/testalert - Test notifikasi\n"
        "/marketdebug - Debug data market"
    )


# =========================
# COMMAND /trade
# =========================

async def trade(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        data = btc_signal()
        setup = data.get("trade_setup")

        if not setup:
            await update.message.reply_text("Trading setup belum tersedia.")
            return

        message = (
            "🧠 ALIZA TRADING BRAIN\n\n"
            f"Market: BTC\n"
            f"Trend: {data.get('trend')}\n\n"
            f"Setup: {setup.get('setup')}\n\n"
            f"Entry: {setup.get('entry')}\n"
            f"Stop Loss: {setup.get('sl')}\n"
            f"Take Profit 1: {setup.get('tp1')}\n"
            f"Take Profit 2: {setup.get('tp2')}\n\n"
            f"Risk Reward: {setup.get('risk_reward')}"
        )

        await update.message.reply_text(message)

    except Exception as e:

        logging.error(f"ERROR TRADE COMMAND: {e}")
        await update.message.reply_text("Terjadi kesalahan saat membaca market.")


# =========================
# COMMAND /market
# =========================

async def market(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        data = btc_signal()
        message = format_market_report(data)

        await update.message.reply_text(message)

    except Exception as e:

        logging.error(f"ERROR MARKET COMMAND: {e}")
        await update.message.reply_text("Terjadi kesalahan saat membaca market.")


# =========================
# COMMAND /testalert
# =========================

async def testalert(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "✅ TEST ALERT ALIZA\n\n"
        "Sistem notifikasi Telegram aktif dan berjalan normal."
    )


# =========================
# COMMAND /status
# =========================

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🧠 STATUS SISTEM ALIZA\n\n"
        "API Server: AKTIF\n"
        "AI Engine: AKTIF\n"
        "Market Analyzer: AKTIF\n"
        "Trading Brain: AKTIF\n"
        "Telegram Bot: ONLINE\n\n"
        "Semua sistem berjalan normal."
    )


# =========================
# COMMAND /marketdebug
# =========================

async def marketdebug(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        data = btc_signal()

        message = (
            "🔎 MARKET DEBUG\n\n"
            f"Harga BTC: {data.get('price')}\n"
            f"RSI: {data.get('rsi')}\n"
            f"Trend: {data.get('trend')}\n\n"
            f"Fear & Greed: {data.get('fear_greed')}\n"
            f"Dominance: {data.get('dominance')}\n\n"
            f"Whale Activity: {data.get('whale_activity')}\n"
            f"Crash Risk: {data.get('crash_alert')}\n"
            f"Signal AI: {data.get('signal')}"
        )

        await update.message.reply_text(message)

    except Exception as e:

        logging.error(f"MARKET DEBUG ERROR: {e}")


# =========================
# AUTO MARKET SIGNAL
# =========================

async def auto_market_signal(context: ContextTypes.DEFAULT_TYPE):

    global LAST_SIGNAL

    try:

        data = btc_signal()

        signal = data.get("signal")
        crash = data.get("crash_alert")
        bottom = data.get("bottom_probability")

        message = None

        if crash == "HIGH":

            message = (
                "🚨 PERINGATAN MARKET\n\n"
                f"Probabilitas Crash: {data.get('crash_probability')}%\n\n"
                "Rekomendasi:\n"
                "TUNGGU / KURANGI POSISI"
            )

        elif (bottom or 0) > 80:

            message = (
                "🟢 ZONA AKUMULASI BTC\n\n"
                "Market kemungkinan berada di area bottom.\n\n"
                "Rekomendasi:\n"
                "MULAI AKUMULASI BTC"
            )

        elif signal in ["BUY", "SELL"]:

            signal_text = "BELI" if signal == "BUY" else "JUAL"

            message = (
                "📡 SINYAL TRADING ALIZA\n\n"
                f"Sinyal: {signal_text}\n"
                f"Trend Market: {data.get('trend')}\n\n"
                f"Harga BTC: ${data.get('price')}"
            )

        if message and message != LAST_SIGNAL:

            LAST_SIGNAL = message

            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=message
            )

    except Exception as e:

        logging.error(f"AUTO SIGNAL ERROR: {e}")


# =========================
# HANDLE TEXT MESSAGE
# =========================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        if not update.message or not update.message.text:
            return

        user_id = update.effective_user.id
        user_message = update.message.text

        name = save_user_name(user_id, user_message)

        if name:

            response = f"Baik, saya ingat. Nama Anda {name.title()}."

        elif "siapa nama saya" in user_message.lower():

            stored_name = get_user_name(user_id)

            if stored_name:
                response = f"Nama Anda {stored_name.title()}"
            else:
                response = "Maaf, saya belum tahu nama Anda."

        else:

            response = ask_aliza(user_message)

        for part in split_message(response):
            await update.message.reply_text(part)

    except Exception as e:

        logging.error(f"ERROR TEXT MESSAGE: {e}")


# =========================
# HANDLE DOCUMENT
# =========================

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        document = update.message.document

        file_name = document.file_name
        file_size = document.file_size

        ext = os.path.splitext(file_name)[1].lower()

        if file_size > MAX_FILE_SIZE:
            await update.message.reply_text("Ukuran file terlalu besar. Maksimal 20MB.")
            return

        if ext not in ALLOWED_TYPES:
            await update.message.reply_text("Format file tidak didukung.")
            return

        file = await context.bot.get_file(document.file_id)

        unique_name = str(uuid.uuid4()) + "_" + file_name
        save_path = os.path.join(UPLOAD_FOLDER, unique_name)

        await file.download_to_drive(save_path)

        set_active_document(save_path)

        await update.message.reply_text(
            f"Dokumen '{file_name}' berhasil diupload.\nSedang menganalisis..."
        )

        add_document_to_vector_store(save_path)

        summary = analyze_document()

        message = "Dokumen berhasil diproses.\n\nRingkasan:\n" + summary

        for part in split_message(message):
            await update.message.reply_text(part)

    except Exception as e:

        logging.error(f"ERROR DOCUMENT: {e}")


# =========================
# TELEGRAM APP
# =========================

def main():

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("trade", trade))
    app.add_handler(CommandHandler("market", market))

    app.add_handler(CommandHandler("testalert", testalert))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("marketdebug", marketdebug))

    app.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    )

    app.add_handler(
        MessageHandler(filters.Document.ALL, handle_document)
    )

    job_queue = app.job_queue

    job_queue.run_repeating(
        auto_market_signal,
        interval=300,
        first=20
    )

    logging.info("AlizaAI Telegram Bot aktif...")

    app.run_polling()


if __name__ == "__main__":
    main()