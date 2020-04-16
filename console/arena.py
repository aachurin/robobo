import logging
import random
import time
from console.trace import trace
from console.utils import wait, find, find_all, click_mouse, get_sample_part, reshaped_sample, resample_loop
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


trace.suppress("arena/game/waiting_finish")
trace.suppress("arena/game/waiting_next")
trace.suppress("arena/dialog/search")


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


ARENA10 = {
    "width": 224,
    "height": 130,
    "state_offset": 80,
    "positions": (
        (528, 86),
        (405, 228),
        (652, 228),
        (283, 369),
        (529, 369),
        (774, 369),
        (159, 510),
        (405, 510),
        (651, 510),
        (898, 510)
    )
}


def start_arena(count=1, kind=None, max_force=None, type=None):
    """Start game.
    `kind`, `max_force` and `type` is used to override default behavior.
    `count` - how many times to start the game
    """
    num = 1
    while count > 0:
        if start_arena_once(num, kind=kind, max_force=max_force, type=type):
            num += 1
            count -= 1


def start_arena_once(num, kind=None, max_force=None, type=None):
    assert kind in (None, "food", "ticket")
    logger.info("start arena #%d", num)
    goto_arena(kind)
    return run_arena(max_force=max_force, type=type)


@resample_loop(min_timeout=1, logger=logger)
def run_arena(max_force, type, *, loop, played=0):
    if max_force is None:
        max_force = config.get("arena:max-force")
    if type is None:
        type = config.get("arena:type")
    state = get_arena_state()
    if state == "arena/game/active":
        if choose_enemy_and_attack(max_force, type):
            played += 1
        # start search and run bu
    elif state == "arena/game/waiting_next":
        logger.info("waiting for next stage", extra={"rate": 1/5})
        loop.retry(False)
    elif state == "arena/game/waiting_finish":
        logger.info("waiting for arena finished", extra={"rate": 1/5})
        loop.retry(False)
    elif state in ("arena/game/victory", "arena/game/defeat"):
        loop.click_and_check("arena/game/back", timeout=3)
    elif state == "arena/game/sleeping":
        loop.click_and_check("arena/game/sleeping_back", timeout=3)
    elif state == "arena/game/finished":
        time.sleep(5)
        if loop.click_and_check(["arena/game/close", "arena/game/close2"], timeout=3):
            return played
    elif state == "arena/check":
        return played
    loop.retry(played=played)


def get_arena_state(*args, **kwargs):
    return wait((
        "arena/game/active",
        "arena/game/finished",
        "arena/game/waiting_next",
        "arena/game/waiting_finish",
        "arena/game/victory",
        "arena/game/defeat",
        "arena/game/sleeping",
        "arena/check"
    ), *args, trace_frame=1, **kwargs)


def get_current_stage(*args, **kwargs):
    stage = wait((
        "arena/game/stage1",
        "arena/game/stage2",
        "arena/game/stage3",
        "arena/game/stage4",
        "arena/game/stage5",
    ), *args, trace_frame=1, **kwargs)
    return {
        "arena/game/stage1": 1,
        "arena/game/stage2": 2,
        "arena/game/stage3": 3,
        "arena/game/stage4": 4,
        "arena/game/stage5": 5
    }.get(stage)


@resample_loop(min_timeout=0.5, logger=logger)
def choose_enemy_and_attack(max_force, type, *, loop):
    if type == 10:
        arena = ARENA10
    else:
        arena = ARENA15

    stage = get_current_stage(2)
    logger.info("current stage: %d", stage)

    slot_width = arena["width"]
    slot_height = arena["height"]
    slot_offset = arena["state_offset"]
    slots_before = []
    slots_after = []
    slots = slots_before
    found_me = False
    for num, (x, y) in enumerate(arena["positions"]):
        slot_sample = get_sample_part(x, y + slot_offset, slot_width, slot_height - slot_offset)
        found = find((
            "arena/game/played_defeat",
            "arena/game/played_win",
            "arena/game/played_me1",
            "arena/game/played_me2",
        ), sample=slot_sample, threshold=0.83)
        if not found:
            slots.append((num, (x + slot_width // 2, y + slot_height // 2)))
        elif found:
            if found in ("arena/game/played_me1", "arena/game/played_me2"):
                found_me = True
                slots = slots_after
                logger.info("enemy %d - looks like it's me", num + 1)
            else:
                logger.info("enemy %d - could not attack", num + 1)

    if stage == 1 or not found_me:
        slots_after = slots_before + slots_after
        slots_before = []

    forces = []
    for num, pos in reversed(slots_before):
        if get_arena_state(1, can_trace=False) != "arena/game/active":
            return False
        click_mouse(*pos, rand_x=40, rand_y=40)
        loop.new_sample()
        if not loop.wait("arena/game/attack", timeout=3.):
            logger.error("enemy %d - looks like it's me!", num + 1)
            continue
        if loop.find("arena/game/can_attack"):
            force = get_enemy_force()
            logger.info("enemy %d - force %d", num + 1, force)
            if force < max_force:
                logger.info("select enemy %d with force %d", num + 1, force)
                loop.click_and_check("arena/game/attack")
                return
            else:
                forces.append((force, (num, pos)))
        else:
            logger.error("enemy %d - could not attack!", num + 1)
        click_mouse(1160, 380, rand_x=50, rand_y=50)
        loop.wait_while("arena/game/attack", timeout=3.)

    for num, pos in slots_after:
        if get_arena_state(1, can_trace=False) != "arena/game/active":
            return False
        click_mouse(*pos, rand_x=40, rand_y=40)
        loop.new_sample()
        if not loop.wait("arena/game/attack", timeout=3.):
            logger.error("enemy %d - looks like it's me!", num + 1)
            continue
        if loop.find("arena/game/can_attack"):
            force = get_enemy_force()
            logger.info("enemy %d - force %d", num + 1, force)
            forces.append((force, (num, pos)))
        else:
            logger.error("enemy %d - could not attack!", num + 1)
        click_mouse(1160, 380, rand_x=50, rand_y=50)
        loop.wait_while("arena/game/attack", timeout=3.)

    forces = sorted(forces)
    if not forces:
        return False

    force, (num, pos) = forces[0]
    logger.info("select enemy %d with force %d", num + 1, force)
    click_mouse(*pos, rand_x=50, rand_y=50)
    loop.click_and_check("arena/game/attack")
    return True


def get_enemy_force(sample=None, convert=int, threshold=None):
    sample = reshaped_sample(left=0.5, top=0.3, bottom=0.4, right=0, sample=sample)
    threshold = threshold or 0.85
    digits = "0123456789"
    nums = []
    for dig in digits:
        nums += [(x.left, dig) for x in find_all("arena/digits/" + dig, sample=sample, threshold=threshold)]
    value = "".join(x[1] for x in sorted(nums))
    return convert(value)


@resample_loop(min_timeout=1, logger=logger, force_resample=True)
def goto_arena(kind=None, *, loop):
    state = get_arena_state(0, can_trace=False)
    if state and state != "arena/check":
        return

    if loop.find("arena/dialog/search"):
        logger.info("still searching", extra={"rate": 1})
        loop.retry(False)

    if loop.find("arena/dialog/opened"):
        loop.click_and_check("arena/dialog/approve", timeout=3)
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
            loop.click("arena/food/ticket", timeout=3)
            loop.retry()

        elif kind == "food" and mode != "arena/food/check":
            loop.click("arena/ticket/food", timeout=3)
            loop.retry()

    loop.click_and_check("arena/start", timeout=3)

    loop.retry()
