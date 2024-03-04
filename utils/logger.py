import os
import sys
import logging
from typing import Optional

LOGS_PATH = "./logs/"

class Logger:
    """Logs info, warning and error messages"""
    if not os.path.exists(LOGS_PATH):
        os.makedirs(LOGS_PATH)
    
    def __init__(self, name: Optional[str]=None) -> None:
        name = __class__.__name__ if name is None else name

        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        s_handler = logging.StreamHandler()
        f_handler = logging.FileHandler(f"{LOGS_PATH}logs.log", "w")

        fmt = logging.Formatter("%(name)s:%(levelname)s - %(message)s")

        s_handler.setFormatter(fmt)
        f_handler.setFormatter(fmt)

        s_handler.setLevel(logging.INFO)
        f_handler.setLevel(logging.INFO)

        self.logger.addHandler(s_handler)
        self.logger.addHandler(f_handler)
    
    def info(self, message: str) -> None:
        self.logger.info(message)
    
    def warn(self, message: str) -> None:
        self.logger.warning(message)
    
    def error(self, message: str, severe: Optional[bool]=False) -> None:
        self.logger.error(message, exc_info=True)

        if severe: sys.exit(1)