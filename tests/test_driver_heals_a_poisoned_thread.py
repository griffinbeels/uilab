"""A stale running-loop marker on the thread must not outlive the session
that left it. See `_heal_stuck_loop` in the playwright driver for the
16-worker cascade this pins (2026-09-01)."""
import asyncio

import pytest

from uilab.driver import get_driver


def test_a_stale_running_loop_marker_is_cleared_and_named():
    """Plant the exact state a failed stop leaves (the marker set, no loop
    actually serving it), then open a browser: it must start, warn, and leave
    the thread clean enough for asyncio.run() afterwards."""
    stale = asyncio.new_event_loop()
    asyncio._set_running_loop(stale)
    try:
        with pytest.warns(RuntimeWarning, match="stale asyncio running-loop marker"):
            with get_driver().launch() as page:
                assert page is not None
    finally:
        asyncio._set_running_loop(None)
        stale.close()
    assert asyncio._get_running_loop() is None
    asyncio.run(asyncio.sleep(0))


def test_a_clean_thread_gets_no_warning(recwarn):
    with get_driver().launch() as page:
        assert page is not None
    assert not [w for w in recwarn if "running-loop marker" in str(w.message)]
    asyncio.run(asyncio.sleep(0))
