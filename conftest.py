"""Root conftest: refuse to run with live credentials; block outbound network.

Policy and rationale: pace-core STANDARDS/testing.md (pace-core#31).
"""
import os
import socket

import pytest

import live_guard

_ROOT = os.path.dirname(os.path.abspath(__file__))
_LOCAL = {"127.0.0.1", "localhost", "::1"}


def pytest_configure(config):
    problems = live_guard.check(os.environ, _ROOT)
    if problems:
        pytest.exit(live_guard.refusal_message(problems), returncode=2)


@pytest.fixture(autouse=True, scope="session")
def _block_outbound_network():
    real = socket.socket.connect

    def guarded(self, address, *a, **k):
        host = address[0] if isinstance(address, tuple) else address
        if host not in _LOCAL:
            raise RuntimeError("outbound network blocked in tests: %r" % (host,))
        return real(self, address, *a, **k)

    socket.socket.connect = guarded
    try:
        yield
    finally:
        socket.socket.connect = real
