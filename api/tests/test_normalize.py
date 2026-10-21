import pytest

from fantasy_api import normalize


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("Carnell Tate", "carnelltate", id="lowercase_and_spaces"),
        pytest.param("    Cam Ward   ", "camward", id="extra_spaces"),
        pytest.param("Ja'Marr Chase", "jamarrchase", id="apostrophe"),
        pytest.param("Ja’Marr Chase", "jamarrchase", id="curly_apostrophe"),  # noqa: RUF001
        pytest.param("Amon-Ra St. Brown", "amonrastbrown", id="hyphen_and_abbreviation"),
        pytest.param("D.J. Moore", "djmoore", id="initials_with_dots"),
        pytest.param("DJ Moore", "djmoore", id="initials_without_dots"),
        pytest.param("Marvin Harrison Jr.", "marvinharrison", id="suffix_jr_dot"),
        pytest.param("Marvin Harrison Jr", "marvinharrison", id="suffix_jr_no_dot"),
        pytest.param("Deebo Samuel Sr.", "deebosamuel", id="suffix_sr"),
        pytest.param("Marvin Harrison, Jr.", "marvinharrison", id="suffix_with_comma"),
        pytest.param("Marvin Harrison, Jr. ", "marvinharrison", id="suffix_with_space"),
        pytest.param("Jermaine Johnson II", "jermainejohnson", id="suffix_ii"),
        pytest.param("Luther Burden III", "lutherburden", id="suffix_iii"),
        pytest.param("Willie Snead IV", "williesnead", id="suffix_iv"),
        pytest.param("Will Fuller V", "willfuller", id="suffix_v"),
        pytest.param("Will FullerV", "willfullerv", id="suffix_does_not_break_v_ending"),
    ],
)
def test_player_name(raw: str, expected: str) -> None:
    assert normalize.player_name(raw) == expected
