import re

_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]")
_SUFFIX = re.compile(r"\s+(?:jr|sr|ii|iii|iv|v)\.?$")


def player_name(name: str) -> str:
    return _NON_ALPHANUMERIC.sub("", _SUFFIX.sub("", name.strip().lower()))
