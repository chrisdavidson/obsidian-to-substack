"""Suite-wide fixtures.

The one thing here exists because the clipboard tests were reading the
machine they ran on.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def neutral_display_server(monkeypatch):
    """Hide the host's display server from every test.

    `clipboard._is_wayland` reads `XDG_SESSION_TYPE` and `WAYLAND_DISPLAY`
    from the real environment, so a test that patches `sys.platform` to
    "linux" and expects the xclip backend gets the wl-copy one instead when
    the suite happens to run on a Wayland desktop. Seven tests failed that
    way on the author's own machine while passing in every X11 session --
    the code under test was fine and the assertions were reading the
    session type of whoever ran them.

    Clearing both is the right default rather than patching seven call
    sites: a unit test declares which platform it is simulating, and
    nothing outside the test may contradict that declaration. The Wayland
    tests set `XDG_SESSION_TYPE` themselves via `patch.dict`, which layers
    on top of this and still works; that opt-in is now the only way any
    test sees Wayland, which is what makes the result the same everywhere.

    Autouse and suite-wide on purpose. Scoping it to the clipboard tests
    would leave the next module free to grow the same dependency silently,
    and this env leak has already shipped once.
    """
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
