import time
import posix_ipc
import socket
import mmap
import random
import logging
import threading
import struct
import numpy as np
import cv2
import settings
from console.config import config
from console.exceptions import ConsoleException


__all__ = (
    "client",
    "set_client_click_timeout",
    "set_client_move_timeout"
)


logger = logging.getLogger(__name__)


class ClientException(ConsoleException):
    logger = "client"


class ClientConnectedException(ClientException):
    pass


class ClientNotConnectedException(ClientException):
    pass


class ClientInvalidScreenSize(ClientException):
    pass


class Inject:
    KEYCODE = 0
    TEXT = 1
    TOUCH_EVENT = 2
    SCROLL_EVENT = 3


class MouseAcion:
    DOWN = 0
    UP = 1
    MOVE = 2


class MouseButton:
    PRIMARY = 1 << 0
    SECONDARY = 1 << 1
    TERTIARY = 1 << 2
    BACK = 1 << 3
    FORWARD = 1 << 4


def to_fixed_point_16(f):
    assert 0.0 <= f <= 1.0
    return max(int(f * 0x10000), 0xffff)


def pack_mouse_event(action, buttons, x, y):
    return struct.pack(
        ">BBqLLHHHL",
        Inject.TOUCH_EVENT,      # 8
        action,                  # 8
        -1,                      # 64 pointer_id = -1
        x,                       # 32
        y,                       # 32
        settings.SCREEN_WIDTH,   # 16
        settings.SCREEN_HEIGHT,  # 16
        0xffff,                  # 16 pressure == 1.0
        buttons                  # 32
    )


class Client:
    video_buffer_name = settings.SCRSHARE_VIDEO_BUFFER_NAME
    video_lock_name = settings.SCRSHARE_VIDEO_LOCK_NAME
    local_port = settings.LOCAL_PORT
    socket = None
    video = None
    video_lock = None
    sample = None
    sample_key = 0
    _connected = False

    def connect(self, timeout=1.):
        if self._connected:
            raise ClientConnectedException("Already connected")
        self.socket = socket.socket()
        self.socket.connect(("127.0.0.1", self.local_port))
        time.sleep(timeout)
        memory = posix_ipc.SharedMemory(self.video_buffer_name)
        self.video = mmap.mmap(memory.fd, memory.size)
        memory.close_fd()
        self.video_lock = posix_ipc.Semaphore(self.video_lock_name)
        self.sample = None
        self.sample_key = 0
        self._connected = True
        try:
            self._check_sample_size()
        except ClientException:
            self.close()
            raise
        threading.Thread(target=self.run_receiver, daemon=True).start()
        return True

    @property
    def connected(self):
        return self._connected

    def _check_sample_size(self):
        sample = self.new_sample()
        if sample.shape != (settings.SCREEN_HEIGHT, settings.SCREEN_WIDTH):
            self.close()
            raise ClientInvalidScreenSize("Expected screen size: (%d, %d), got: (%d, %d)" % (
                settings.SCREEN_WIDTH,
                settings.SCREEN_HEIGHT,
                sample.shape[1],
                sample.shape[0]
            ))

    def close(self):
        if self._connected:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.socket.close()
            self.video.close()
            self.video_lock.close()
            self.socket = None
            self.video = None
            self.video_lock = None
            self._connected = False

    def __del__(self):
        self.close()

    def run_receiver(self):
        device_msg_serialized_max_size = 4096
        logger.info("Receiver started.")
        while 1:
            data = self.socket.recv(device_msg_serialized_max_size)
            if not data:
                break
        logger.info("Receiver stopped.")

    def ensure_connected(self):
        if not self._connected:
            raise ClientNotConnectedException("Not connected")

    def get_sample(self):
        self.ensure_connected()
        video = self.video
        video.seek(0)
        with self.video_lock:
            key, width, height = np.frombuffer(video.read(12), dtype=np.uint32)
            if key != self.sample_key:
                sample = np.frombuffer(video.read(width * height), dtype=np.uint8)
                sample = sample.reshape((height, width))
                self.sample = sample
                self.sample_key = key
        return self.sample

    def new_sample(self):
        cur_key = self.sample_key
        sample = self.get_sample()
        while cur_key == self.sample_key:
            time.sleep(settings.SCRSHARE_RENDER_INTERVAL / 1000.)
            sample = self.get_sample()
        return sample

    def mouse_down(self, x, y):
        self.socket.send(pack_mouse_event(MouseAcion.DOWN, MouseButton.PRIMARY, x, y))

    def mouse_up(self, x, y):
        self.socket.send(pack_mouse_event(MouseAcion.UP, MouseButton.PRIMARY, x, y))

    def mouse_move(self, x, y):
        self.socket.send(pack_mouse_event(MouseAcion.MOVE, MouseButton.PRIMARY, x, y))

    def click(self, x, y, rand_x=None, rand_y=None):
        if rand_x:
            x += random.randint(-rand_x, rand_x)
        if rand_y:
            y += random.randint(-rand_y, rand_y)
        self.mouse_down(x, y)
        time.sleep(config.get("client:click-timeout"))
        self.mouse_up(x, y)
        return (x, y)

    def move(self, x1, y1, x2, y2):
        c = 8
        dx = (x2 - x1) / c
        dy = (y2 - y1) / c
        self.mouse_down(x1, y1)
        time.sleep(0.05)
        move_timeout = config.get("client:move-timeout")
        for n in range(c):
            self.mouse_move(int(x1 + dx * n), int(y1 + dy * n))
            time.sleep(move_timeout)
        time.sleep(0.05)
        self.mouse_up(x2, y2)


client = Client()

config.add_option("client:click-timeout", type=float, min_value=0.001, max_value=1., default=0.15)
config.add_option("client:move-timeout", type=float, min_value=0.001, max_value=1., default=0.02)


def set_client_click_timeout(value):
    config.set("client:click-timeout", value)


def set_client_move_timeout(value):
    config.set("client:move-timeout", value)
