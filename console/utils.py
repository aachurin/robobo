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

    def __init__(self, name, left, top, width, height):
        self.name = name
        self.left = left
        self.top = top
        self.width = width
        self.height = height

    def set_logger(self, logger):
        self.logger = logger
        return self

    @property
    def right(self):
        return self.left + self.width - 1

    @property
    def bottom(self):
        return self.top + self.height - 1

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

    def find(self, sample=None, threshold=None):
        threshold = threshold or settings.IMAGE_SEARCH_THESHOLD
        matches = self.find_all(sample=sample, threshold=threshold)
        if matches:
            return matches[0]

    def find_all(self, sample=None, threshold=None):
        threshold = threshold or settings.IMAGE_SEARCH_THESHOLD
        if sample is None:
            sample = client.get_sample()
        res = cv2.matchTemplate(sample, self.img, cv2.TM_CCOEFF_NORMED)
        loc = np.where(res >= threshold)
        return self.without_intersections(zip(*loc[::-1]))

    def without_intersections(self, matches):
        width, height = self.img.shape[::-1]
        width23 = width * 2 / 3
        height23 = height * 2 / 3
        filtered = []
        for left, top in matches:
            for match in filtered:
                if ((match.left - width23) < left < (match.left + width23) and
                        (match.top - height23) < top < (match.top + height23)):
                    break
            else:
                filtered.append(Match(self.name, left, top, width, height))
        return filtered


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


def wait(targets, timeout=..., logger=None, threshold=None):
    if isinstance(targets, str):
        targets = (targets,)
    if timeout is ...:
        timeout = config.get("utils:default-wait-timeout")
    target_names = ", ".join(targets)
    tm = time.time()
    while 1:
        for t in targets:
            match = templates[t].find(threshold=threshold)
            if match:
                return match.set_logger(logger)
        if timeout is not None and (time.time() - tm) > timeout:
            return NoMatch(targets).set_logger(logger)
        if logger and tm - time.time() > 2.:
            logger.info("waiting [%s]", target_names, extra={"rate": 1/2})
        client.new_sample()


def wait_while(targets, timeout=..., logger=None):
    if isinstance(targets, str):
        targets = (targets,)
    if timeout is ...:
        timeout = config.get("utils:default-wait-timeout")
    tm = time.time()
    attempt = 1
    while 1:
        for t in targets:
            match = templates[t].find()
            if match:
                if logger and tm - time.time() > 2.:
                    logger.info("still can find [%s]", match, extra={"rate": 1 / 2})
                break
        else:
            return True
        if timeout is not None and (time.time() - tm) > timeout:
            return False
        client.new_sample()
        attempt += 1


def find(targets, logger=None, sample=None, threshold=None):
    if isinstance(targets, str):
        targets = (targets,)
    for t in targets:
        match = templates[t].find(sample=sample, threshold=threshold)
        if match:
            return match.set_logger(logger)
    return NoMatch(targets).set_logger(logger)


def find_all(target, logger=None, sample=None, threshold=None):
    return [x.set_logger(logger) for x in templates[target].find_all(sample=sample, threshold=threshold)]


def click(targets, timeout=..., logger=None):
    return wait(targets, timeout=timeout, logger=logger).click()


def click_and_check(targets, timeout=..., check_timeout=None, logger=None):
    if wait(targets, timeout=timeout, logger=logger).click():
        check_timeout = check_timeout or timeout
        return wait_while(targets, timeout=check_timeout, logger=logger)
    return False


click_mouse = client.click
mouse_move = client.move


def reshaped_sample(left=0, top=0, right=0, bottom=0, sample=None):
    assert 0 <= left <= 1
    assert 0 <= top <= 1
    assert 0 <= right <= 1
    assert 0 <= bottom <= 1
    if sample is None:
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

    def reset_timer(self):
        self._last_time = time.time()

    def new_sample(self):
        if self._min_timeout:
            delta = time.time() - self._last_time
            if delta < self._min_timeout:
                time.sleep(self._min_timeout - delta)
        client.new_sample()
        self.reset_timer()

    def wait(self, *args, **kwargs):
        return wait(*args, **kwargs, logger=self._logger)

    def wait_while(self, *args, **kwargs):
        return wait_while(*args, **kwargs, logger=self._logger)

    def find(self, *args, **kwargs):
        return find(*args, **kwargs, logger=self._logger)

    def find_all(self, *args, **kwargs):
        return find_all(*args, **kwargs, logger=self._logger)

    def click(self, *args, **kwargs):
        return click(*args, **kwargs, logger=self._logger)

    def click_and_check(self, *args, **kwargs):
        return click_and_check(*args, **kwargs, logger=self._logger)

    @staticmethod
    def retry(log_retry=True):
        raise Retry(log_retry)


def resample_loop(min_timeout=0, logger=None):
    loop_obj = LoopObj(min_timeout=min_timeout, logger=logger)

    def wrapper(fn):
        def loop(*args, **kwargs):
            loop_obj.reset_timer()
            while 1:
                try:
                    return fn(*args, **kwargs, loop=loop_obj)
                except Retry as e:
                    if logger and e.log_retry:
                        logger.info("resample and retry", extra={"rate": 1/1.})
                loop_obj.new_sample()
        return loop
    return wrapper


config.add_option("utils:default-wait-timeout", type=float, min_value=0.1, max_value=100, default=10.)
