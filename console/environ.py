import time
from console import adb
from console.client import client, ClientException
from console.watchdog import start_watchdog


__all__ = ("reboot",)


def reboot():
    client.close()
    if not adb.run_server():
        return
    time.sleep(1)
    if adb.processes_started():
        try:
            client.connect()
        except ClientException:
            adb.kill_server()
            raise
        start_watchdog()
