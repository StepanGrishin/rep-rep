import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
MODEL_DIR = Path(os.getenv("MODEL_DIR", "models"))

START_YEAR = int(os.getenv("START_YEAR", "2015"))
END_YEAR = int(os.getenv("END_YEAR", "2026"))

# Для Telegram. 0 = показывать все матчи, для которых модель может посчитать прогноз.
MIN_COMMON_OPPONENTS = int(os.getenv("MIN_COMMON_OPPONENTS", "0"))

# Модель
TEST_START_YEAR = int(os.getenv("TEST_START_YEAR", "2024"))
VALIDATION_START_YEAR = int(os.getenv("VALIDATION_START_YEAR", "2022"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
