import time

from kargah.adapters.process import run_stoppable


def test_a_stop_request_ends_a_long_command_quickly(tmp_path):
    started, flips = time.monotonic(), iter([False, True])
    result = run_stoppable(["sleep", "60"], tmp_path, "", {}, 120, lambda: next(flips, True), poll_s=0.5)
    assert result.stopped and not result.timed_out
    assert time.monotonic() - started < 15


def test_a_command_that_runs_too_long_times_out(tmp_path):
    result = run_stoppable(["sleep", "60"], tmp_path, "", {}, 1, poll_s=0.5)
    assert result.timed_out and not result.stopped


def test_a_finished_command_returns_its_output_and_gets_the_input(tmp_path):
    result = run_stoppable(["cat"], tmp_path, "hello", {}, 30, lambda: False, poll_s=0.5)
    assert (result.returncode, result.stdout, result.stopped, result.timed_out) == (0, "hello", False, False)


def test_children_of_the_command_are_stopped_too(tmp_path):
    pidfile = tmp_path / "child.pid"
    script = f"sleep 60 & echo $! > {pidfile}; wait"
    flips = iter([False, True])
    result = run_stoppable(["bash", "-c", script], tmp_path, "", {}, 120, lambda: next(flips, True), poll_s=0.5)
    pid = int(pidfile.read_text())
    time.sleep(0.2)
    assert result.stopped
    import os
    try:
        os.kill(pid, 0)
        alive = True
    except ProcessLookupError:
        alive = False
    assert not alive
