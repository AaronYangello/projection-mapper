import random

import pytest
from projection_show.config.models import Project
from projection_show.scheduler import Scheduler, ShuffleBag


def test_shuffle_bag_visits_every_item_and_avoids_boundary_repeats():
    bag = ShuffleBag(["a", "b", "c", "d"], random.Random(55))
    results = [bag.pop() for _ in range(4000)]
    assert all(a != b for a, b in zip(results, results[1:], strict=False))
    assert all(set(results[i : i + 4]) == {"a", "b", "c", "d"} for i in range(0, 4000, 4))


def test_single_and_empty_bags():
    bag = ShuffleBag(["only"], random.Random(0))
    assert [bag.pop() for _ in range(10)] == ["only"] * 10
    with pytest.raises(ValueError):
        ShuffleBag([], random.Random(0)).pop()


def timed(demo):
    data = demo.model_dump()
    data["show"].update(
        fade_in_seconds=2,
        hold_seconds={"min": 3, "max": 3},
        fade_out_seconds=2,
        gap_seconds={"min": 1, "max": 1},
    )
    return Scheduler(Project.model_validate(data))


def test_fades_hold_gap_and_queue_are_time_based(demo):
    scheduler = timed(demo)
    planned = scheduler.queue.copy()
    scheduler.tick(0)
    assert scheduler.current == planned[0]
    scheduler.tick(1)
    assert scheduler.phase()[:2] == ("FADING_IN", 0.5)
    scheduler.tick(1)
    assert scheduler.phase()[:2] == ("FOREGROUND", 1)
    scheduler.tick(4)
    assert scheduler.phase()[:2] == ("FADING_OUT", 0.5)
    scheduler.tick(1)
    assert scheduler.phase()[:2] == ("GAP", 0)
    scheduler.tick(1)
    assert scheduler.current == planned[1]
    assert len(scheduler.queue) == demo.show.queue_length


def test_frame_rate_independence_and_catch_up(demo):
    slow, fast = timed(demo), timed(demo)
    slow.tick(35.5)
    for _ in range(355):
        fast.tick(0.1)
    assert slow.current == fast.current
    assert slow.elapsed == pytest.approx(fast.elapsed)
    assert slow.queue == fast.queue


def test_forced_fade_starts_at_current_opacity(demo):
    scheduler = timed(demo)
    scheduler.tick(1)
    scheduler.fade_out()
    assert scheduler.phase()[:2] == ("FADING_OUT", 0.5)
    scheduler.tick(1)
    assert scheduler.phase()[:2] == ("FADING_OUT", 0.25)
    scheduler.tick(2)
    assert scheduler.current.id == 2


def test_zero_fades_and_gap_are_safe(demo):
    demo.show.fade_in_seconds = demo.show.fade_out_seconds = 0
    demo.show.gap_seconds.min = demo.show.gap_seconds.max = 0
    scheduler = Scheduler(demo)
    scheduler.tick(0)
    assert scheduler.phase()[:2] == ("FOREGROUND", 1)
    scheduler.fade_out()
    scheduler.tick(0)
    assert scheduler.current.id == 2


def test_eligibility_is_generic_and_respects_projectors(demo):
    demo.projectors[0].enabled = False
    demo.surfaces[2].foreground_enabled = False
    demo.surfaces[3].enabled = False
    demo.surfaces[4].tags = ["excluded"]
    demo.show.surfaces.exclude_tags = ["excluded"]
    demo.scenes[0].enabled = False
    scheduler = Scheduler(demo)
    assert scheduler.surfaces.items == ["plane-6", "plane-7"]
    assert "tidal" not in scheduler.scenes.items
    assert all(c.surface_id in scheduler.surfaces.items for c in scheduler.queue)


def test_empty_eligibility_stays_idle(demo):
    demo.scenes = []
    scheduler = Scheduler(demo)
    scheduler.tick(1000)
    assert scheduler.snapshot()["phase"] == "IDLE"
    assert scheduler.queue == []
