from collections.abc import Callable

import pytest
from textual.content import Content
from textual.widget import Widget


@pytest.fixture
def text_of() -> Callable[[Widget], str]:
    return lambda widget: str(widget.render())


@pytest.fixture
def span_styles() -> Callable[[Content], list[str]]:
    return lambda content: [str(span.style) for span in content.spans]
