import logging
import os
from logging.handlers import TimedRotatingFileHandler

def setup_logger(log_file: str):
    os.makedirs("logs", exist_ok=True)

    rotating_file_handler = TimedRotatingFileHandler(
        filename=f"logs/{log_file}",
        when="midnight",
        interval=1,
        backupCount=7,  # 7日分保持し、超過分は自動削除
        encoding="utf-8",
    )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[
            rotating_file_handler,
            logging.StreamHandler(),
        ],
        force=True,
    )
