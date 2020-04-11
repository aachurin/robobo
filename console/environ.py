import time
from console import adb
from console.client import client, ClientException


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
