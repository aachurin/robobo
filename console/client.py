import time
import socket
import random
import logging
import struct
import numpy as np
import settings
from console.config import config
from console.exceptions import ConsoleException
from console import threads


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
    server_port = settings.SERVER_PORT
    receiver_port = settings.RECEIVER_PORT
    _sample = None
    _sample_key = None
    _control_socket = None
    _receiver_socket = None
    _videobuff = None
    _connected = False

    def connect(self, timeout=3.):
        if self._connected:
            raise ClientConnectedException("Already connected")
        self._thead_container = threads.ThreadContainer()
        self._sample = None
        self._sample_key = None
        self._receiver_socket = socket.socket()
        self._thead_container.run(self.video_receiver)
        self._control_socket = socket.socket()
        self._control_socket.connect(("127.0.0.1", self.server_port))
        self._thead_container.run(self.control_receiver)
        time.sleep(timeout)
        self._connected = True
        try:
            self._check_sample_size()
        except ClientException:
            self.close()
            raise
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
            self._thead_container.close()
            self._thead_container = None
            try:
                self._control_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._receiver_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._control_socket.close()
            self._receiver_socket.close()
            self._control_socket = None
            self._receiver_socket = None
            self._connected = False

    def __del__(self):
        self.close()

    def video_receiver(self):
        logger.info("Video receiver started.")
        self._receiver_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._receiver_socket.bind(("127.0.0.1", self.receiver_port))
        self._receiver_socket.listen()
        conn, addr = self._receiver_socket.accept()

        def recvall(sock, n):
            # Helper function to recv n bytes or return None if EOF is hit
            data = bytearray()
            while len(data) < n:
                packet = sock.recv(n - len(data))
                if not packet:
                    return None
                data.extend(packet)
            return data

        with conn:
            logger.info("Video receiver connected to %s", addr)
            key = 0
            while True:
                frame_info = recvall(conn, 12)
                if not frame_info:
                    break
                size, width, height = np.frombuffer(frame_info, dtype=np.uint32)
                data = recvall(conn, size.item())
                if not data:
                    break
                key += 1
                self._videobuff = (key, width.item(), height.item(), data)

        logger.info("Video receiver stopped.")

    def control_receiver(self):
        device_msg_serialized_max_size = 4096
        logger.info("Control receiver started.")
        while 1:
            data = self._control_socket.recv(device_msg_serialized_max_size)
            if not data:
                break
        logger.info("Control receiver stopped.")

    def ensure_connected(self):
        if not self._connected:
            raise ClientNotConnectedException("Not connected")

    @property
    def videobuf(self):
        if self._connected:
            return self._videobuff

    def get_sample(self):
        self.ensure_connected()
        key, width, height, data = self._videobuff
        # key, width, height = np.frombuffer(video.read(12), dtype=np.uint32)
        if (height, width) != (settings.SCREEN_HEIGHT, settings.SCREEN_WIDTH):
            logger.error("Invalid frame size.")
        elif key != self._sample_key:
            sample = np.frombuffer(data, dtype=np.uint8)
            sample = sample.reshape((height, width))
            self._sample = sample
            self._sample_key = key
        return self._sample

    def new_sample(self):
        cur_key = self._sample_key
        sample = self.get_sample()
        while cur_key == self._sample_key:
            time.sleep(settings.SCRSHARE_RENDER_INTERVAL / 1000.)
            sample = self.get_sample()
        return sample

    def mouse_down(self, x, y):
        self._control_socket.send(pack_mouse_event(MouseAcion.DOWN, MouseButton.PRIMARY, x, y))

    def mouse_up(self, x, y):
        self._control_socket.send(pack_mouse_event(MouseAcion.UP, MouseButton.PRIMARY, x, y))

    def mouse_move(self, x, y):
        self._control_socket.send(pack_mouse_event(MouseAcion.MOVE, MouseButton.PRIMARY, x, y))

    def click(self, x, y, rand_x=None, rand_y=None):
        if rand_x:
            x += random.randint(-rand_x, rand_x)
        if rand_y:
            y += random.randint(-rand_y, rand_y)
        self.mouse_down(x, y)
        time.sleep(config.get("client:click-timeout"))
        self.mouse_up(x, y)
        return x, y

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
