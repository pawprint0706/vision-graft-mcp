"""Main-thread marshaling (plan §2.4.2).

ScreenCaptureKit / AppKit must run on the main thread. When the HTTP host
handles a tool call on a background thread inside the tray app, capture work is
marshaled to the main thread's run loop. In the bare CLI (already on the main
thread, no run loop) the call runs directly.
"""

from __future__ import annotations

import threading
from typing import Callable, TypeVar

T = TypeVar("T")


def is_main_thread() -> bool:
    return threading.current_thread() is threading.main_thread()


def post_to_main(func: Callable[[], object]) -> None:
    """Schedule `func` on the main run loop without waiting (fire-and-forget).

    Use for UI that may stay open arbitrarily long (e.g. a modal dialog), where
    waiting on the worker thread would be wrong.
    """
    if is_main_thread():
        func()
        return
    try:
        from PyObjCTools import AppHelper  # noqa: PLC0415
    except ImportError:
        func()
        return
    AppHelper.callAfter(func)


def run_on_main(func: Callable[[], T], timeout: float = 30.0) -> T:
    if is_main_thread():
        return func()
    try:
        from PyObjCTools import AppHelper  # noqa: PLC0415
    except ImportError:
        # No Cocoa run loop available — best effort, run inline.
        return func()

    box: dict[str, object] = {}
    done = threading.Event()

    def wrapper() -> None:
        try:
            box["result"] = func()
        except BaseException as exc:  # noqa: BLE001 — re-raised on caller thread
            box["error"] = exc
        finally:
            done.set()

    AppHelper.callAfter(wrapper)
    if not done.wait(timeout):
        raise TimeoutError("Main-thread work did not complete in time.")
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box["result"]  # type: ignore[return-value]
