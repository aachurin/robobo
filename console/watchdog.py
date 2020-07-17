import logging
import threading
import time
from console.utils import wait, click, click_mouse
from console.client import client

try:
    import playsound
except ImportError:
    playsound = None


__all__ = (
    "start_watchdog",
    "stop_watchdog",
)


logger = logging.getLogger(__name__)


def watchdog_runner():
    logger.info("Watchdog started")

    states = (
        "common/hummer1",
        "common/magnifier1",
        "common/under_attack",
        "common/after_attack",
        "common/another_device",
        "common/sleeping",
        "common/captcha",
    )

    while _watchdog_thread is not None:
        time.sleep(3)
        if not client.connected:
            continue
        state = wait(states, timeout=0, logger=logger, threshold=0.65)
        if not state:
            continue
        if state == "common/hummer1":
            logger.info("Hummer")
            click_mouse(500, 400, rand_x=100, rand_y=100)
        elif state == "common/magnifier1":
            logger.info("Magnifier")
            click_mouse(500, 400, rand_x=100, rand_y=100)
        elif state == "common/under_attack":
            logger.info("Under attack")
            click("common/update_button", timeout=0, logger=logger)
        elif state == "common/after_attack":
            logger.info("After attack")
            click("common/ok_button", timeout=0, logger=logger)
        elif state == "common/another_device":
            logger.info("Another device")
            click("common/try_again_button", timeout=0, logger=logger)
        elif state == "common/sleeping":
            logger.info("I'm sleeping, really?")
            click("common/sleeping_back", timeout=0, logger=logger)
        elif state == "common/captcha":
            logger.info("Captcha alarm!")
            if playsound:
                playsound.playsound("sounds/alarm.mp3")
            else:
                for x in range(6):
                    time.sleep(1)
                    print("\007")

    logger.info("Watchdog stopped")


_watchdog_thread = None


def start_watchdog():
    global _watchdog_thread
    if not _watchdog_thread:
        _watchdog_thread = threading.Thread(target=watchdog_runner, daemon=True)
        _watchdog_thread.start()


def stop_watchdog():
    global _watchdog_thread
    if _watchdog_thread:
        thread, _watchdog_thread = _watchdog_thread, None
        thread.join()
