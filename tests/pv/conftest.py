from collections.abc import Callable

import pytest

from phoebus_tui.pv import PV


@pytest.fixture
def bare_pv() -> Callable[[type[PV], str], PV]:
    """Construct a backend PV without connecting it, to exercise its value handling."""

    def make(cls: type[PV], name: str) -> PV:
        pv = cls.__new__(cls)
        PV.__init__(pv, name)
        return pv

    return make
