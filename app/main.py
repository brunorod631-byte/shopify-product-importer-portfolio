import asyncio
import logging

from telegram.error import NetworkError
from telegram.ext import Application
from app.config import get_settings
from app.database import init_db
from app.logging_config import configure_logging
from app.services.import_service import ImportService
from app.telegram.handlers import register
def main():
    s = get_settings(); configure_logging(s); sessions = init_db(s)
    if not s.configured:
        raise SystemExit("Faltan TELEGRAM_BOT_TOKEN y TELEGRAM_ALLOWED_USER_IDS en .env")

    logger = logging.getLogger(__name__)
    while True:
        app = Application.builder().token(s.telegram_bot_token).build()
        app.bot_data.update(settings=s, sessions=sessions, import_service=ImportService(s, sessions))
        register(app)
        try:
            app.run_polling(allowed_updates=Update.ALL_TYPES)
            return
        except (NetworkError, OSError) as exc:
            logger.exception("Conexión perdida; el bot se reiniciará en 15 segundos: %s", exc)
            asyncio.run(asyncio.sleep(15))
if __name__=="__main__":
    from telegram import Update
    main()
