import os
import time
import cv2
import numpy as np
import settings
import logging
from console.client import client
from console.config import config


__all__ = ("wait", "find", "find_all", "click", "click_mouse", "mouse_move",
           "reshaped_sample", "get_sample", "resample_loop")


logger = logging.getLogger(__name__)


class Match:

    logger = None

    def __init__(self, name, pos, dim):
        self.name = name
        self.pos = pos
        self.dim = dim

    def set_logger(self, logger):
        self.logger = logger
        return self

    @property
    def left(self):
        return self.pos[0]

    @property
    def right(self):
        return self.pos[0] + self.dim[0] - 1

    @property
    def top(self):
        return self.pos[1]

    @property
    def bottom(self):
        return self.pos[1] + self.dim[1] - 1

    @property
    def width(self):
        return self.dim[0]

    @property
    def height(self):
        return self.dim[1]

    def click(self):
        x = self.left + self.width // 2
        y = self.top + self.height // 2
        client.click(x, y)
        (self.logger or logger).info("click on [%r]", self)
        return True

    def __str__(self):
        return self.name

    def __bool__(self):
        return True

    def __repr__(self):
        return "%s (%d %d %dx%d)" % (
            self.name, self.left, self.top, self.width, self.height
        )

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        if isinstance(other, str):
            return self.name == other
        return self.name == other.name


class NoMatch:

    logger = None

    class Origin:
        def __init__(self, origin):
            self.origin = origin

        def __repr__(self):
            return ", ".join(self.origin)

        __str__ = __repr__

    def __init__(self, origin):
        self.origin = self.Origin(origin)

    def set_logger(self, logger):
        self.logger = logger
        return self

    def click(self):
        (self.logger or logger).error("could not click [%r]", self.origin)
        return False

    def __bool__(self):
        return False

    def __repr__(self):
        return "<nomatch>"

    def __str__(self):
        return "<nomatch>"

    def __eq__(self, o):
        return False

    def __hash__(self):
        return 0


class Template:
    def __init__(self, name, img):
        self.name = name
        self.img = img

    def find(self, sample=None, threshold=settings.IMAGE_SEARCH_THESHOLD):
        matches = self.find_all(sample=sample, threshold=threshold)
        if matches:
            return matches[0]

    def find_all(self, sample=None, threshold=settings.IMAGE_SEARCH_THESHOLD):
        if sample is None:
            sample = client.get_sample()
        res = cv2.matchTemplate(sample, self.img, cv2.TM_CCOEFF_NORMED)
        loc = np.where(res >= threshold)
        matches = list(zip(*loc[::-1]))
        dim = self.img.shape[::-1]
        return [Match(self.name, match, dim) for match in matches]


class Templates(dict):
    def __missing__(self, key):
        if isinstance(key, Template):
            return self[key.name]
        img = cv2.imread(os.path.join(settings.TEMPLATE_DIR, key + ".png"))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        tpl = Template(key, img)
        self[key] = tpl
        return tpl


templates = Templates()


def wait(targets, timeout=..., logger=None):
    if isinstance(targets, str):
        targets = (targets,)
    if timeout is ...:
        timeout = config.get("utils:default-wait-timeout")
    tm = time.time()
    while 1:
        for t in targets:
            match = templates[t].find()
            if match:
                return match.set_logger(logger)
        if timeout is not None and (time.time() - tm) > timeout:
            return NoMatch(targets).set_logger(logger)
        client.new_sample()


def find(targets, logger=None, sample=None):
    if isinstance(targets, str):
        targets = (targets,)
    for t in targets:
        match = templates[t].find(sample=sample)
        if match:
            return match.set_logger(logger)
    return NoMatch(targets).set_logger(logger)


def find_all(target, logger=None, sample=None):
    return [x.set_logger(logger) for x in templates[target].find_all(sample=sample)]


def click(targets, timeout=0, logger=None):
    return wait(targets, logger=logger, timeout=timeout).click()


click_mouse = client.click
mouse_move = client.move


def reshaped_sample(left=0, top=0, right=0, bottom=0):
    assert 0 <= left <= 1
    assert 0 <= top <= 1
    assert 0 <= right <= 1
    assert 0 <= bottom <= 1
    sample = client.get_sample()
    w, h = sample.shape[::-1]
    left = int(w * left)
    right = int(w * (1 - right))
    top = int(h * top)
    bottom = int(h * (1 - bottom))
    return sample[top:bottom, left:right]


get_sample = client.get_sample


class Retry(Exception):
    def __init__(self, log_retry=True):
        self.log_retry = log_retry


class LoopObj:
    def __init__(self, min_timeout=0, logger=None):
        self._min_timeout = min_timeout
        self._last_time = 0
        self._logger = logger

    def sleep(self):
        if self._min_timeout:
            delta = time.time() - self._last_time
            if delta < self._min_timeout:
                time.sleep(self._min_timeout - delta)

    def new_sample(self):
        client.new_sample()
        self._last_time = time.time()

    def wait(self, *args, **kwargs):
        return wait(*args, **kwargs, logger=self._logger)

    def find(self, *args, **kwargs):
        return find(*args, **kwargs, logger=self._logger)

    def find_all(self, *args, **kwargs):
        return find_all(*args, **kwargs, logger=self._logger)

    def click(self,  *args, **kwargs):
        return click(*args, **kwargs, logger=self._logger)

    @staticmethod
    def retry(log_retry=True):
        raise Retry(log_retry)


def resample_loop(min_timeout=0, logger=None):
    loop_obj = LoopObj(min_timeout=min_timeout, logger=logger)

    def wrapper(fn):
        def loop(*args, **kwargs):
            while 1:
                loop_obj.sleep()
                try:
                    return fn(*args, **kwargs, loop=loop_obj)
                except Retry as e:
                    if logger and e.log_retry:
                        logger.info("resample and retry", extra={"rate": 1/1.})
                loop_obj.new_sample()
        return loop
    return wrapper


config.add_option("utils:default-wait-timeout", type=float, min_value=0.1, max_value=100, default=10.)
