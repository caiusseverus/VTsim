"""Shared pytest fixtures for VT native simulation tests."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
from typing import Any

import pytest

# Ensure project root is on sys.path so that webapp.* imports work during test collection.
_root = Path(__file__).resolve().parents[1]
_root_str = str(_root)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)

# If VTSIM_VT_DIR is set, route custom_components.versatile_thermostat imports to the
# versioned VT directory before any test files are collected.
_vt_dir_env = os.environ.get("VTSIM_VT_DIR", "")
if _vt_dir_env:
    # Inject the versioned VT's custom_components/ dir into the already-loaded
    # custom_components package path. VTsim's own custom_components/__init__.py
    # makes it a regular package that wins over sys.path search order; manipulating
    # __path__ directly ensures the versioned VT is found first for sub-imports.
    import custom_components as _cc_pkg
    _vt_cc_dir = str(Path(_vt_dir_env).resolve().parent)  # the custom_components/ dir
    if _vt_cc_dir not in _cc_pkg.__path__:
        _cc_pkg.__path__.insert(0, _vt_cc_dir)
    # Keep the grandparent on sys.path as a fallback for direct imports
    _vt_parent = str(Path(_vt_dir_env).resolve().parents[1])
    if _vt_parent not in sys.path:
        sys.path.insert(0, _vt_parent)


class _PipeSelfWakeSelectorLoop(asyncio.SelectorEventLoop):
    """Selector loop that wakes via os.pipe() instead of socketpair().

    Some sandboxed environments block socket send operations (even on a local
    socketpair), which breaks asyncio's default cross-thread wakeup mechanism.
    Home Assistant frequently schedules callbacks thread-safely; if the wakeup
    fails, the loop can deadlock while "idle".
    """

    def _make_self_pipe(self) -> None:
        self._ssock, self._csock = os.pipe()
        os.set_blocking(self._ssock, False)
        os.set_blocking(self._csock, False)
        self._internal_fds += 1
        self._add_reader(self._ssock, self._read_from_self)

    def _close_self_pipe(self) -> None:
        if self._ssock is None or self._csock is None:
            return
        self._remove_reader(self._ssock)
        os.close(self._ssock)
        self._ssock = None
        os.close(self._csock)
        self._csock = None
        self._internal_fds -= 1

    def _read_from_self(self) -> None:
        while True:
            try:
                data = os.read(self._ssock, 4096)
                if not data:
                    break
                self._process_self_data(data)
            except InterruptedError:
                continue
            except BlockingIOError:
                break

    def _write_to_self(self) -> None:
        csock = self._csock
        if csock is None:
            return
        try:
            os.write(csock, b"\0")
        except OSError:
            # If this fails, cross-thread wakeups are broken; but failing hard
            # here makes debugging impossible. Let higher-level timeouts fail.
            return


class _PipeSelfWakePolicy(asyncio.DefaultEventLoopPolicy):
    def new_event_loop(self) -> asyncio.AbstractEventLoop:
        return _PipeSelfWakeSelectorLoop()


def _patch_homeassistant_event_loop_policy() -> None:
    """Patch HA's event loop policy to build a loop that wakes without sockets.

    Home Assistant configures a HassEventLoopPolicy during startup/fixtures.
    In some sandboxed environments, asyncio's default socketpair-based self-pipe
    wakeup can fail (EPERM on socket send), which breaks call_soon_threadsafe()
    and can deadlock setup. Using an os.pipe-based self-wake loop avoids that.
    """
    try:
        import homeassistant.runner as ha_runner
    except Exception:
        return

    class _PipeHassEventLoopPolicy(ha_runner.HassEventLoopPolicy):  # type: ignore[misc]
        def new_event_loop(self) -> asyncio.AbstractEventLoop:
            loop: asyncio.AbstractEventLoop = _PipeSelfWakeSelectorLoop()
            loop.set_exception_handler(ha_runner._async_loop_exception_handler)
            if self.debug:
                loop.set_debug(True)

            executor = ha_runner.InterruptibleThreadPoolExecutor(
                thread_name_prefix="SyncWorker", max_workers=ha_runner.MAX_EXECUTOR_WORKERS
            )
            loop.set_default_executor(executor)
            loop.set_default_executor = ha_runner.warn_use(  # type: ignore[method-assign]
                loop.set_default_executor, "sets default executor on the event loop"
            )
            loop.time = ha_runner.monotonic  # type: ignore[method-assign]
            return loop

    ha_runner.HassEventLoopPolicy = _PipeHassEventLoopPolicy  # type: ignore[assignment]


_patch_homeassistant_event_loop_policy()

@pytest.fixture(autouse=True)
def verify_cleanup() -> None:
    """Local override: tolerate integration background threads."""
    yield


@pytest.fixture
def expected_lingering_timers() -> bool:
    """Allow HA's delayed storage writes scheduled during integration setup."""
    return True


@pytest.fixture
def expected_lingering_tasks() -> bool:
    """Allow long-lived background tasks created by VT."""
    return True


@pytest.fixture(autouse=True)
def _ensure_custom_components_on_syspath() -> None:
    """Ensure project root (containing custom_components/) is importable."""
    root = Path(__file__).resolve().parents[1]
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


@pytest.fixture(scope="session")
def metrics_accumulator() -> list[dict[str, Any]]:
    """Accumulate per-scenario metrics across the session; write CSV at the end.

    Using a session-scoped fixture ensures the CSV is written once with all
    completed scenarios, rather than being overwritten after each test.
    """
    # Import here to avoid a circular dependency at module load time.
    _root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(_root))
    sys.path.insert(0, str(_root / "tests"))
    from sim.analysis import write_summary_csv  # noqa: PLC0415

    acc: list[dict[str, Any]] = []
    yield acc

    results_dir = _root / "results"
    results_dir.mkdir(exist_ok=True)
    if acc:
        write_summary_csv(acc, results_dir / "summary.csv")
