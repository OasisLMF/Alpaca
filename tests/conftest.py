import pytest

GREEN = "\x1b[32m"
RESET = "\x1b[0m"
COLOUR_CODES = {"green": "32"}


def _colour(text, colour):
    return f"\x1b[{COLOUR_CODES[colour]}m{text}{RESET}"


def _highlighted(text):
    return [part.split(RESET)[0].strip() for part in text.split(GREEN)[1:]]


@pytest.fixture
def in_green(monkeypatch):
    """Colour report output whatever the test's stdout is, and read back what was coloured.

    termcolor caches its one-off decision about whether the terminal can take colour the
    first time anything is coloured, so a test that sets FORCE_COLOR passes or fails
    depending on which tests ran before it. Replacing the colouring call itself keeps that
    out of the picture.

    Returns:
        callable: Takes report output and returns the list of values highlighted in it, in
            the order they appear, stripped of the padding they were coloured with.
    """
    monkeypatch.setattr("alpaca.benchmark.timing.colored", _colour)
    return _highlighted
