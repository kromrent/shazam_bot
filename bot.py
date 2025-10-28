#!/usr/bin/env python3
import logging
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters,CallbackQueryHandler
from musicbot.config import TG_TOKEN, init_dirs
from musicbot.db import init_db
from musicbot.handlers import start, handle_video, handle_link, handle_text, handle_choice

def main():
    logging.getLogger("HybridMusicBot").info("🚀 Hybrid bot starting...")
    init_dirs()
    init_db()

    app = ApplicationBuilder().token(TG_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VIDEO & ~filters.COMMAND, handle_video))

    # ссылки
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'https?://'), handle_link))

    # обычный текст (название трека)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'https?://'), handle_text))
    app.add_handler(CallbackQueryHandler(handle_choice))
    app.run_polling()

if __name__ == "__main__":
    main()
