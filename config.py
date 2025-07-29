import json
import logging
from pathlib import Path

logger = logging.getLogger("bot")
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

formatter = logging.Formatter(
fmt="%(asctime)s | %(levelname)-8s | %(filename)s:%(lineno)d | %(message)s",
datefmt="%d.%m.%Y %H:%M:%S"
)
console_handler.setFormatter(formatter)
file_handler = logging.FileHandler(Path(__file__).parent / 'logs' / 'bot.log')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)

def get_config():
    with open('config.json') as f:
        config_str = f.read()
        config_dict = json.loads(config_str)
        return config_dict