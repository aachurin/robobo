import os
import sys
import logging
import cv2
import time
from datetime import datetime
import settings
from console import __version__


print("Robot v%s" % __version__)
print()

from console.logging import setup_logging
setup_logging()
del setup_logging

from console.exceptions import ConsoleException
from console.client import client
from console.config import *
from console.environ import *
from console.utils import *
from console.navigation import *
from console.arena import *
from console.watchdog import *
from console.trace import trace


def _exception_hook(exctype, value, traceback):
    if isinstance(value, ConsoleException):
        if value.logger and not config.get("traceback", False):
            logging.getLogger(value.logger).error(value.msg)
        else:
            logging.getLogger("console").error(value.msg)
    else:
        sys.__excepthook__(exctype, value, traceback)


sys.excepthook = _exception_hook


def save_sample(filename=None, *, sample=None, directory=settings.SAMPLE_DIR):
    if sample is None:
        sample = get_sample()
    if filename is None:
        filename = datetime.now().strftime("%Y%m%d_%H_%S_%f.png")
    os.makedirs(directory, exist_ok=True)
    cv2.imwrite(os.path.join(directory, filename), sample)


def read_sample(filename, directory=settings.SAMPLE_DIR):
    img = cv2.imread(os.path.join(directory, filename))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


reboot()
