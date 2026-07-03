import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

BASE_DOWNLOAD_FOLDER = "downloads"
FONTS_FOLDER = "fonts"
os.makedirs(BASE_DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(FONTS_FOLDER, exist_ok=True)
os.makedirs("logs", exist_ok=True)

# إعداد نظام Logging متقدم مع التدوير (Rotating)
log_handler = RotatingFileHandler(
    "logs/bot.log", maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[log_handler, logging.StreamHandler()]
)
logger = logging.getLogger("NosoosBot")