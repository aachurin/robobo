import logging
import threading
import time
from console.utils import wait, click
from console.client import client


__all__ = (
    "start_watchdog",
    "stop_watchdog",
)


logger = logging.getLogger(__name__)


def watchdog_runner():
    logger.info("Watchdog started")
    states = (
        "common/under_attack",
        "common/after_attack",
        "common/another_device"
    )

    while _watchdog_thread is not None:
        time.sleep(3)
        if not client.connected:
            continue
        state = wait(states, timeout=0, logger=logger)
        if not state:
            continue
        if state == "common/under_attack":
            logger.info("Under attack")
            click("common/update_button", timeout=0, logger=logger)
        elif state == "common/after_attack":
            logger.info("After attack")
            click("common/ok_button", timeout=0, logger=logger)
        elif state == "common/another_device":
            logger.info("Another device")
            click("common/try_again_button", timeout=0, logger=logger)

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
