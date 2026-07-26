import logging
from logging.handlers import RotatingFileHandler

from app.config import ROOT, Settings


class SecretFilter(logging.Filter):
    def __init__(self, secrets: list[str]):
        super().__init__()
        self.secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self.secrets:
            message = message.replace(secret, "[REDACTED]")
        record.msg, record.args = message, ()
        return True


def configure_logging(settings: Settings) -> None:
    (ROOT / "logs").mkdir(exist_ok=True)
    handler = RotatingFileHandler(ROOT / "logs" / "bot.log", maxBytes=2_000_000, backupCount=3)
    handler.addFilter(SecretFilter([
        settings.telegram_bot_token,
        settings.shopify_client_secret,
        settings.shopify_admin_access_token,
    ]))
    logging.basicConfig(level=settings.log_level, handlers=[handler, logging.StreamHandler()],
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
