from memory_tracker import MemoryTracker

from kargah.orchestrator.interrupt import InterruptWatch


def test_the_label_is_asked_at_most_once_per_interval_and_stays_set():
    tracker, now = MemoryTracker(), [0.0]
    n = tracker.open_ticket("t")
    calls = []
    real = tracker.get_ticket
    tracker.get_ticket = lambda number: calls.append(number) or real(number)      # type: ignore[method-assign]
    watch = InterruptWatch(tracker, n, 30, lambda: now[0])
    assert not watch() and not watch()
    assert len(calls) == 1                       # second call inside the interval is cached
    tracker.add_label(n, "interrupt")
    assert not watch()                           # still cached
    now[0] = 31
    assert watch() and watch()
    assert len(calls) == 2                       # once set it stays set without more API calls
