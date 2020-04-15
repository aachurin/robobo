import logging
from console.utils import wait, find_all, click_mouse, reshaped_sample, resample_loop
from console.config import config
from console.navigation import navigation


__all__ = (
    "start_arena",
    "set_arena_type",
    "set_arena_max_force",
    "set_arena_kind"
)


logger = logging.getLogger(__name__)
config.add_option("arena:max-force", type=int, min_value=0, default=250000)
config.add_option("arena:type", choices=(10, 15), default=10)
config.add_option("arena:kind", choices=(None, "food", "ticket"), default=None)


def set_arena_type(value):
    """Set arena type (10 or 15).

    Examples:
        set_arena_type(10)
        set_arena_type(15)
    """
    config.set("arena:type", value)


def set_arena_max_force(value):
    """Set max enemy force.

    Examples:
        set_arena_max_force(3000000)
    """
    config.set("arena:max-force", value)


def set_arena_kind(value):
    """Set arena kind ("food", "ticket" or None).
    Examples:
        set_arena_kind("food")
        set_arena_kind("ticket")
        set_arena_kind(None)
    """
    config.set("arena:kind", value)


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


def start_arena(count=1, kind=None, max_force=None, type=None):
    """Start game.
    `kind`, `max_force` and `type` is used to override default behavior.
    `count` - how many times to start the game
    """
    for _ in range(count):
        start_arena_once(kind=kind, max_force=max_force, type=type)


def start_arena_once(kind=None, max_force=None, type=None):
    assert kind in (None, "food", "ticket")
    goto_arena(kind)
    run_arena(max_force=max_force, type=type)


@resample_loop(min_timeout=1, logger=logger)
def run_arena(max_force, type, *, loop):
    if max_force is None:
        max_force = config.get("arena:max-force")
    if type is None:
        type = config.get("arena:type")
    state = get_arena_state()
    if state == "arena/game/active":
        choose_enemy_and_attack(max_force, type)
        # start search and run bu
    elif state == "arena/game/waiting.next":
        logger.info("waiting for next stage", extra={"rate": 1/5})
        loop.retry(False)
    elif state == "arena/game/waiting.finish":
        logger.info("waiting for arena finished", extra={"rate": 1/5})
        loop.retry(False)
    elif state in ("arena/game/victory", "arena/game/defeat"):
        loop.click_and_check("arena/game/back", timeout=2)
    elif state == "arena/game/sleeping":
        loop.click_and_check("arena/game/sleeping_back", timeout=2)
    elif state == "arena/game/finished":
        loop.click_and_check(["arena/game/close", "arena/game/close2"], timeout=2)
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


@resample_loop(min_timeout=0.5, logger=logger)
def choose_enemy_and_attack(max_force, type, *, loop):
    if type == 10:
        capacity = 10
        positions = ARENA10_POS
    else:
        capacity = 15
        positions = ARENA15_POS

    forces1 = []
    forces2 = []
    forces = forces1

    for num, pos in enumerate(positions, 1):
        if get_arena_state(1) != "arena/game/active":
            return False
        click_mouse(*pos)
        loop.new_sample()
        if not loop.wait("arena/game/attack", timeout=2.):
            logger.info("enemy %d - looks like it's me", num)
            forces = forces2
            continue
        elif loop.find("arena/game/can_attack"):
            force = get_enemy_force()
            logger.info("enemy %d - force %d", num, force)
            forces.append((force, pos))
        else:
            logger.info("enemy %d - could not attack", num)
        click_mouse(15, 15)
        loop.wait_while("arena/game/attack", timeout=2.)

    # simplest stage check
    phase = capacity - len(forces1 + forces2)
    forces1 = sorted(forces1)
    forces2 = sorted(forces2)
    logger.info("current stage: %d", phase)
    if forces1 and phase == 1 and forces1[0][0] < max_force:
        enemy = forces1[0]
    else:
        enemy = sorted(forces1 + forces2)[0]
    logger.info("select enemy with force %d", enemy[0])
    click_mouse(*enemy[1])
    loop.click_and_check("arena/game/attack")


def get_enemy_force(sample=None, convert=int, threshold=None):
    sample = reshaped_sample(left=0.5, top=0.3, bottom=0.4, right=0, sample=sample)
    threshold = threshold or 0.85
    digits = "0123456789"
    nums = []
    for dig in digits:
        nums += [(x.left, dig) for x in find_all("arena/digits/" + dig, sample=sample, threshold=threshold)]
    value = "".join(x[1] for x in sorted(nums))
    return convert(value)


@resample_loop(min_timeout=1, logger=logger)
def goto_arena(kind=None, *, loop):
    if get_arena_state(0):
        return

    if loop.find("arena/dialog/search"):
        logger.info("still searching", extra={"rate": 1})
        loop.retry(False)

    if loop.find("arena/dialog/opened"):
        loop.click_and_check("arena/dialog/approve", timeout=2)
        loop.retry()

    loc = navigation.get_loc()
    if not loc:
        loop.retry()

    if loc != "arena":
        navigation.goto("arena")

    loc = navigation.get_loc()
    if loc != "arena":
        loop.retry()

    kind = kind or config.get("arena:kind")
    if kind is not None:
        mode = loop.find([
            "arena/food/check",
            "arena/ticket/check"
        ])
        if not mode:
            loop.retry()

        if kind == "ticket" and mode != "arena/ticket/check":
            loop.click("arena/food/ticket", timeout=2)
            loop.retry()

        elif kind == "food" and mode != "arena/food/check":
            loop.click("arena/ticket/food", timeout=2)
            loop.retry()

    loop.click_and_check("arena/start", timeout=2)

    loop.retry()
