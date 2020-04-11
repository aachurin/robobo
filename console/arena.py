import logging
from console.utils import wait, find_all, click_mouse, reshaped_sample, resample_loop
from console.config import config
from console.navigation import navigation


__all__ = ("start_arena",)


logger = logging.getLogger(__name__)
config.add_option("arena:max-force", type=int, min_value=0, default=250000)
config.add_option("arena:arena-type", type=int, choices=(10, 15), default=10)


ARENA10_POS = (
    (645, 150),
    (520, 290),
    (777, 290),
    (395, 430),
    (645, 430),
    (890, 430),
    (275, 570),
    (525, 570),
    (777, 570),
    (1115, 570),
)


def start_arena(count=1, kind=None, max_force=None, arena_type=None):
    for _ in range(count):
        start_arena_once(kind=kind, max_force=max_force, arena_type=arena_type)


def start_arena_once(kind=None, max_force=None, arena_type=None):
    assert kind in (None, "food", "ticket")
    goto_arena(kind)
    run_arena(max_force=max_force, arena_type=arena_type)


@resample_loop(min_timeout=1, logger=logger)
def run_arena(max_force, arena_type, *, loop):
    if max_force is None:
        max_force = config.get("arena:max-force")
    if arena_type is None:
        arena_type = config.get("arena:arena-type")

    state = get_arena_state()
    if state == "arena/game/active":
        choose_enemy_and_attack(max_force, arena_type)
        # start search and run bu
    elif state == "arena/game/waiting.next":
        logger.info("waiting for next stage", extra={"rate": 1/5})
        loop.retry(False)
    elif state == "arena/game/waiting.finish":
        logger.info("waiting for arena finished", extra={"rate": 1/5})
        loop.retry(False)
    elif state == "arena/game/victory":
        loop.click("arena/game/back", timeout=1)
    elif state == "arena/game/defeat":
        loop.click("arena/game/back", timeout=1)
    elif state == "arena/game/sleeping":
        loop.click("arena/game/sleeping_back", timeout=1)
    elif state == "arena/game/finished":
        if loop.click(["arena/game/close", "arena/game/close2"], timeout=1):
            return
    loop.retry()


def get_arena_state(timeout=...):
    # 1150x128 - забрать награду
    return wait((
        "arena/game/active",
        "arena/game/finished",
        "arena/game/waiting.next",
        "arena/game/waiting.finish",
        "arena/game/victory",
        "arena/game/defeat",
        "arena/game/sleeping"
    ), timeout=timeout)


@resample_loop(logger=logger)
def choose_enemy_and_attack(max_force, arena_type, *, loop):
    if arena_type == 10:
        positions = ARENA10_POS
    else:
        positions = ARENA15_POS

    forces1 = []
    forces2 = []
    forces = forces1

    for num, pos in enumerate(positions, 1):
        click_mouse(*pos)
        if not loop.wait("arena/game/attack", timeout=2.):
            logger.info("enemy %d - looks like it's me", num)
            forces = forces2
        elif loop.find("arena/game/can_attack"):
            force = get_enemy_force()
            logger.info("enemy %d - force %d", num, force)
            forces.append((force, pos))
        else:
            logger.info("enemy %d - could not attack", num)
        click_mouse(15, 15)
        if not loop.wait("arena/game/active"):
            return False

    forces1 = sorted(forces1)
    forces2 = sorted(forces2)
    if forces1 and forces1[0][0] < max_force:
        enemy = forces1[0]
    else:
        enemy = sorted(forces1 + forces2)[0]
    logger.info("select enemy with force %d", enemy[0])
    click_mouse(*enemy[1])
    return loop.wait(["arena/game/attack"]).click()


def get_enemy_force():
    sample = reshaped_sample(left=0.5, top=0.3, bottom=0.4, right=0.2)
    digits = "0123456789"
    nums = []
    for dig in digits:
        nums += [(x.left, dig) for x in find_all("arena/digits/" + dig, sample=sample)]
    value = "".join(x[1] for x in sorted(nums))
    return int(value)


@resample_loop(min_timeout=1, logger=logger)
def goto_arena(kind=None, *, loop):
    if get_arena_state(0):
        return

    if loop.find("arena/dialog/search"):
        logger.info("still searching", extra={"rate": 1})
        loop.retry(False)

    if loop.find("arena/dialog/opened"):
        loop.click("arena/dialog/approve")
        loop.retry()

    loc = navigation.get_loc()
    if not loc:
        loop.retry()

    if loc != "arena":
        navigation.goto("arena")

    loc = navigation.get_loc()
    if loc != "arena":
        loop.retry()

    if kind is not None:
        choose_arena_mode(kind)

    loop.wait([
        "arena/start"
    ]).click()

    loop.retry()


@resample_loop(min_timeout=1.)
def choose_arena_mode(kind, *, loop):
    assert kind in ("food", "ticket")
    mode = loop.find([
        "arena/food/check",
        "arena/ticket/check"
    ])

    if not mode:
        loop.retry()

    if ((kind == "ticket" and mode == "arena/ticket/check") or
            (kind == "food" and mode == "arena/food/check")):
        return

    if kind == "ticket":
        loop.click("arena/food/ticket")
    elif kind == "food":
        loop.click("arena/ticket/food")

    loop.retry()
