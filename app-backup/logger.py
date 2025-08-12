#========================================================================================#
#                                       IDLEARN                                          #
#                                      logger.py                                         #
#========================================================================================#

# Filename: logger.py
# Author: diomir0
# Date of creation: 05 Jul 2025

# This script contains the pipeline for extracting the text from an input PDF, running the 
# summarization, the generation of question-answer pairs, and the generation of Anki cards
# from these pairs.

import logging
import os
import datetime

 # Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)

# Configure logger
logger = logging.getLogger("idlearn_logger")
logger.setLevel(logging.DEBUG)  # Or INFO / WARNING

# File handler
file_handler = logging.FileHandler("logs/idlearn{}.log".format(datetime.datetime), mode='a', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)

# Optional: also log to console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Formatter
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Avoid duplicate handlers
if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
