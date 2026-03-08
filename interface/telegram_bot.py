import os
import sys
import uuid
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
        "Anda bisa:\n"
        "• bertanya apa saja\n"
        "• mengirim dokumen untuk dianalisis\n"
        "• bertanya tentang dokumen yang dikirim"
    )


# =========================
# HANDLE TEXT MESSAGE
# =========================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        if update.message is None or update.message.text is None:
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

        print("ERROR TEXT MESSAGE:", e)

        await update.message.reply_text(
            "Terjadi kesalahan saat memproses pesan."
        )


# =========================
# HANDLE DOCUMENT
# =========================

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        if update.message is None or update.message.document is None:
            return

        document = update.message.document

        file_name = document.file_name
        file_size = document.file_size

        print("Menerima file:", file_name)

        ext = os.path.splitext(file_name)[1].lower()

        # =========================
        # VALIDASI FILE
        # =========================

        if file_size > MAX_FILE_SIZE:

            await update.message.reply_text(
                "Ukuran file terlalu besar. Maksimal 20MB."
            )
            return

        if ext not in ALLOWED_TYPES:

            await update.message.reply_text(
                "Format file tidak didukung."
            )
            return

        # =========================
        # DOWNLOAD FILE
        # =========================

        file = await context.bot.get_file(document.file_id)

        unique_name = str(uuid.uuid4()) + "_" + file_name

        save_path = os.path.join(UPLOAD_FOLDER, unique_name)

        await file.download_to_drive(save_path)

        if not os.path.exists(save_path):

            await update.message.reply_text(
                "Gagal menyimpan dokumen."
            )
            return

        print("File disimpan di:", save_path)

        # =========================
        # SET ACTIVE DOCUMENT
        # =========================

        set_active_document(save_path)

        await update.message.reply_text(
            f"Dokumen '{file_name}' berhasil diupload.\n"
            "Sedang menganalisis dokumen..."
        )

        # =========================
        # UPDATE VECTOR DATABASE
        # =========================

        add_document_to_vector_store(save_path)

        # =========================
        # ANALYZE DOCUMENT
        # =========================

        summary = analyze_document()

        message = "Dokumen berhasil diproses.\n\nRingkasan:\n" + summary

        for part in split_message(message):

            await update.message.reply_text(part)

    except Exception as e:

        print("ERROR DOCUMENT:", e)

        await update.message.reply_text(
            "Terjadi kesalahan saat memproses dokumen."
        )


# =========================
# TELEGRAM APP
# =========================

def main():

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    )

    app.add_handler(
        MessageHandler(filters.Document.ALL, handle_document)
    )

    print("AlizaAI Telegram Bot aktif...")

    app.run_polling()


# =========================
# ENTRY POINT
# =========================

if __name__ == "__main__":
    main()