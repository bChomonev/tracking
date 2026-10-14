import pytest

from corridor.ingest.fotmob import role_from_position_id


@pytest.mark.parametrize(
    ("pos_id", "usual", "role"),
    [
        (11, 0, "GK"),
        (32, 1, "FB"),  # right-back in a back four
        (34, 1, "CB"),
        (33, 1, "CB"),  # right centre-back in a back three
        (38, 1, "FB"),
        (62, 1, "FB"),  # wing-back who is a defender by trade
        (62, 3, "W"),  # forward used on the wide midfield lane
        (64, 2, "CM"),
        (85, 2, "AM"),
        (83, 3, "W"),
        (103, 3, "W"),
        (105, 3, "ST"),
        (115, 3, "ST"),
        (None, 2, None),
    ],
)
def test_role_from_position_id(pos_id, usual, role):
    assert role_from_position_id(pos_id, usual) == role
