import time
import logging
import settings
from console.utils import resample_loop, wait, click, mouse_move


__all__ = ("navigation", )


logger = logging.getLogger(__name__)


class Navigation:

    def __init__(self):
        self._transitions = {}
        self._location_check = {}
        self._check_to_location = {}

    def get_loc(self, timeout=0):
        check = wait(self._check_to_location.keys(), timeout=timeout)
        if not check:
            return None
        return self._check_to_location[check]

    @resample_loop(logger=logger)
    def goto(self, loc, *, loop):
        curloc = self.get_loc()
        if not curloc:
            logger.error(
                "don't know how to get from unknown location to %r", loc,
                extra={"rate": 1}
            )
            return False
        logger.info("location %r", curloc)
        if loc == curloc:
            return True
        transition = self.get_transition(curloc, loc)
        if not transition:
            logger.error(
                "don't know how to get from %r to %r", curloc, loc,
                extra={"rate": 1}
            )
            return False
        transition()
        loop.retry()

    def add_location(self, loc, check):
        assert loc not in self._location_check and check not in self._check_to_location
        self._location_check[loc] = check
        self._check_to_location[check] = loc

    def add_transition(self, from_loc, to_loc):
        assert from_loc in self._location_check and to_loc in self._location_check

        def wrapper(action):
            def transition():
                logger.info("go to %r", to_loc)
                if action():
                    wait(self._location_check[to_loc])
            self._transitions[(from_loc, to_loc)] = transition
            return transition
        return wrapper

    def get_transition(self, from_loc, to_loc):
        return self._transitions.get((from_loc, to_loc))

    def setup(self):
        found = 1
        while found:
            found = 0
            paths = list(self._transitions.keys())
            for k in paths:
                for v in paths:
                    if k[0] == v[1] or (k[0], v[1]) in self._transitions:
                        continue
                    elif k[1] == v[0]:
                        found += 1
                        self._transitions[(k[0], v[1])] = self._transitions[k]


navigation = Navigation()
navigation.add_location("home", check="home/map")
navigation.add_location("map", check="map/home")
navigation.add_location("arena", check="arena/check")


@navigation.add_transition("home", "map")
def _transition():
    return click("home/map", logger=logger)


@navigation.add_transition("map", "home")
def _transition():
    return click("map/home", logger=logger)


@navigation.add_transition("map", "arena")
def _transition():
    mouse_move(50, 50, settings.SCREEN_WIDTH - 50, 50)
    time.sleep(0.5)
    return click("map/arena", logger=logger)


@navigation.add_transition("arena", "map")
def _transition():
    return click("arena/close", logger=logger)


navigation.setup()
