import subprocess
import atexit
import logging
import threading
import time
import signal
import settings
from console.config import config


config.add_option("adb:device", type=str, default=settings.ADB_DEVICE)


logger = logging.getLogger(__name__)


def log_out_before_stop_word(process, name, word):
    while True:
        output = process.stdout.readline()
        if output == "" and process.poll() is not None:
            return process.returncode
        if output:
            output = output.strip()
            if output == word:
                return True
            logger.info("%s: %s", name, output.strip())


class ProcessWatch(threading.Thread):
    def __init__(self, *args, name, process, **kwargs):
        super().__init__(*args, **kwargs)
        self.process_name = name
        self.process = process

    def run(self):
        code = log_out_before_stop_word(self.process, self.process_name, "")
        logger.info("%s: stopped with code %d", self.process_name, code)


def run_command_ex(args):
    complete = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = complete.stdout.decode("utf-8")
    for line in output.splitlines():
        line = line.strip()
        if line:
            logger.info(line.strip())
    return complete.returncode == 0, output


def run_command(args):
    return run_command_ex(args)[0]


def get_attached_devices():
    success, output = run_command_ex(["adb", "devices"])
    if not success:
        return
    ret = []
    for x in output.splitlines():
        x = x.strip()
        if x:
            if x.startswith("*"):
                continue
            if x.lower().startswith("list of"):
                continue
            ret.append(x.split())
    return ret


def connect_to_device():
    output = get_attached_devices()
    if output is None:
        logger.error("Can't get list of connected devices.")
        return False
    adb_device = config.get("adb:device")
    connected = adb_device in [x[0] for x in output]
    if not connected:
        success, output = run_command_ex(["adb", "connect", adb_device])
        if not success or "failed" in output:
            logger.error("Can't connect to device (start Nox or Bluestacks).")
            return False
    return True


def push_server():
    return run_command([
        "adb",
        "-s",
        config.get("adb:device"),
        "push",
        settings.ADB_SERVER_FILENAME,
        settings.ADB_DEVICE_SERVER_PATH
    ])


def enable_tunnel():
    return run_command([
        "adb",
        "-s",
        config.get("adb:device"),
        "forward",
        f"tcp:{settings.LOCAL_PORT}",
        f"localabstract:{settings.ADB_SOCKET_NAME}"
    ])


def ignore_sigin():
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def execute_process(args):
    return subprocess.Popen(args,
                            preexec_fn=ignore_sigin,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            close_fds=True,
                            encoding="utf-8")


def execute_server():
    args = [
        "adb",
        "-s",
        config.get("adb:device"),
        "shell",
        f"CLASSPATH={settings.ADB_DEVICE_SERVER_PATH}",
        "app_process",
        "/",
        "com.genymobile.scrcpy.Server",
        "1.12.1",
        "0",      # maxsize
        f"{settings.SERVER_BIT_RATE}",
        f"{settings.SERVER_MAX_FPS}",
        "true",   # tunnel forwarding
        "-",      # crop
        "true",   # always send frame meta (packet boundaries + timestamp)
        "true"    # controls
    ]
    process = execute_process(args)
    ProcessWatch(process=process, name="scrcpy.Server", daemon=True).start()
    return process


def execute_scrshare():
    args = [
        "scrshare",
        "-p",
        f"{settings.LOCAL_PORT}",
        "-i",
        f"{settings.SCRSHARE_RENDER_INTERVAL}",
        "-l",
        f"{settings.SCRSHARE_LOG_LEVEL}",
    ]
    process = execute_process(args)
    # здесь магия, сервер, что залили через adb ждет 2 соединения
    # первое - это видео поток
    # второе - это контроль
    # и вот тут надо ждать, пока scrshare не приконнектится первым, иначе пиздос
    # scrshare специально логирует @socket_connected
    log_out_before_stop_word(process, "scrshare", "@socket_connected")
    ProcessWatch(process=process, name="scrshare", daemon=True).start()
    return process


_server_proc = None
_scrshare_proc = None


def kill_server():
    if _server_proc:
        _server_proc.terminate()
    if _scrshare_proc:
        _scrshare_proc.terminate()


def run_server():
    global _server_proc, _scrshare_proc
    atexit.unregister(kill_server)
    atexit.register(kill_server)
    kill_server()
    if not connect_to_device():
        return False
    if not push_server():
        return False
    if not enable_tunnel():
        return False
    _server_proc = execute_server()
    time.sleep(1.)
    _scrshare_proc = execute_scrshare()
    return True


def processes_started():
    if _server_proc and _scrshare_proc:
        return _server_proc.poll() is None and _scrshare_proc.poll() is None
    return False
