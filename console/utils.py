import os
import time
import cv2
import numpy as np
import settings
import logging
from console.client import client
from console.config import config
from console.trace import trace


__all__ = ("wait", "find", "find_all", "click", "click_mouse", "mouse_move",
           "reshaped_sample", "get_sample_part", "get_sample", "resample_loop",
           "sample_from_file")


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
        w2 = self.width // 2
        h2 = self.height // 2
        x = self.left + w2
        y = self.top + h2
        rand_x = 0 if w2 < 10 else w2 // 2
        rand_y = 0 if h2 < 10 else h2 // 2
        point = client.click(x, y, rand_x=rand_x, rand_y=rand_y)
        (self.logger or logger).info("click on [%r, %r]", self, point)
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

    @property
    def name(self):
        return repr(self.origin)

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
        threshold = threshold or settings.IMAGE_SEARCH_TRHESHOLD
        matches = self.find_all(sample=sample, threshold=threshold)
        if matches:
            return matches[0]

    def find_all(self, sample=None, threshold=None):
        threshold = threshold or settings.IMAGE_SEARCH_TRHESHOLD
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


def wait(
        targets,
        timeout=...,
        logger=None,
        threshold=None,
        can_trace=True,
        trace_frame=0
):
    trace_frame += 1
    if isinstance(targets, str):
        targets = (targets,)
    if timeout is ...:
        timeout = config.get("utils:default-wait-timeout")
    target_names = ", ".join(targets)
    tm = time.time()
    while 1:
        sample = client.get_sample()
        for t in targets:
            match = templates[t].find(sample=sample, threshold=threshold)
            if match:
                if can_trace:
                    trace.trace("<done>", sample, match, trace_frame=trace_frame)
                return match.set_logger(logger)
        if timeout is not None and (time.time() - tm) > timeout:
            match = NoMatch(targets).set_logger(logger)
            if can_trace:
                trace.trace("<timeout>", sample, match, trace_frame=trace_frame)
            return match
        if logger and tm - time.time() > 2.:
            logger.info("waiting [%s]", target_names, extra={"rate": 1/2})
        client.new_sample()


def wait_while(
        targets,
        timeout=...,
        logger=None,
        threshold=None,
        can_trace=True,
        trace_frame=0
):
    trace_frame += 1
    if isinstance(targets, str):
        targets = (targets,)
    if timeout is ...:
        timeout = config.get("utils:default-wait-timeout")
    tm = time.time()
    attempt = 1
    while 1:
        sample = client.get_sample()
        for t in targets:
            match = templates[t].find(sample=sample, threshold=threshold)
            if match:
                if logger and tm - time.time() > 2.:
                    logger.info("still can find [%s]", match, extra={"rate": 1 / 2})
                break
        else:
            if can_trace:
                match = NoMatch(targets)
                trace.trace("<done>", sample, match, trace_frame=trace_frame)
            return True
        if timeout is not None and (time.time() - tm) > timeout:
            if can_trace:
                trace.trace("<timeout>", sample, match, trace_frame=trace_frame)
            return False
        client.new_sample()
        attempt += 1


def find(
        targets,
        logger=None,
        sample=None,
        threshold=None,
        can_trace=True,
        trace_frame=0
):
    trace_frame += 1
    if isinstance(targets, str):
        targets = (targets,)
    if sample is None:
        sample = client.get_sample()
    for t in targets:
        match = templates[t].find(sample=sample, threshold=threshold)
        if match:
            if can_trace:
                trace.trace("<done>", sample, match, trace_frame=trace_frame)
            return match.set_logger(logger)
    return NoMatch(targets).set_logger(logger)


def find_all(target, logger=None, sample=None, threshold=None):
    return [x.set_logger(logger) for x in templates[target].find_all(sample=sample, threshold=threshold)]


def click(*args, trace_frame=0, **kwargs):
    trace_frame += 1
    return wait(*args, trace_frame=trace_frame, **kwargs).click()


def click_and_check(*args, timeout=..., check_timeout=..., trace_frame=0, **kwargs):
    trace_frame += 1
    clicked = wait(*args, timeout=timeout, trace_frame=trace_frame, **kwargs).click()
    if clicked:
        return wait_while(*args, timeout=check_timeout, trace_frame=trace_frame, **kwargs)
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


def get_sample_part(x, y, width, height, sample=None):
    if sample is None:
        sample = client.get_sample()
    return sample[y:y + height, x:x + width]


get_sample = client.get_sample


class Retry(Exception):
    def __init__(self, log_retry=True, kwargs=None):
        self.log_retry = log_retry
        self.kwargs = kwargs


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

    def wait(self, *args, trace_frame=0, **kwargs):
        trace_frame += 1
        return wait(*args, **kwargs, logger=self._logger, trace_frame=trace_frame)

    def wait_while(self, *args, trace_frame=0, **kwargs):
        trace_frame += 1
        return wait_while(*args, **kwargs, logger=self._logger, trace_frame=trace_frame)

    def find(self, *args, trace_frame=0, **kwargs):
        trace_frame += 1
        return find(*args, **kwargs, logger=self._logger, trace_frame=trace_frame)

    def find_all(self, *args, **kwargs):
        return find_all(*args, **kwargs, logger=self._logger)

    def click(self, *args, trace_frame=0, **kwargs):
        trace_frame += 1
        return click(*args, **kwargs, logger=self._logger, trace_frame=trace_frame)

    def click_and_check(self, *args, trace_frame=0, **kwargs):
        trace_frame += 1
        return click_and_check(*args, **kwargs, logger=self._logger, trace_frame=trace_frame)

    @staticmethod
    def retry(log_retry=True, **kwargs):
        raise Retry(log_retry, kwargs)


def resample_loop(min_timeout=0, logger=None, force_resample=False):
    loop_obj = LoopObj(min_timeout=min_timeout, logger=logger)

    def wrapper(fn):
        def loop(*args, **kwargs):
            if force_resample:
                loop_obj.new_sample()
            else:
                loop_obj.reset_timer()
            while 1:
                try:
                    return fn(*args, **kwargs, loop=loop_obj)
                except Retry as e:
                    if logger and e.log_retry:
                        logger.info("resample and retry", extra={"rate": 1/1.})
                    kwargs.update(e.kwargs or {})
                loop_obj.new_sample()
        return loop
    return wrapper


def sample_from_file(key):
    img = cv2.imread(os.path.join(settings.SAMPLE_DIR, key + ".png"))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


config.add_option("utils:default-wait-timeout", type=float, min_value=0.1, max_value=100, default=10.)
