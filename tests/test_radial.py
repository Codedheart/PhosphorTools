import math

import pytest

from phosphor.radial import away_angle, bbox, fan

SCREEN = (0, 0, 1920, 1040)      # 1080p minus a taskbar
R = 22                           # button radius


def inside(pts, area=SCREEN, r=R):
    l, t, rr, b = area
    return all(l + r <= x <= rr - r and t + r <= y <= b - r for x, y in pts)


def centroid(pts):
    return sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)


@pytest.mark.parametrize("corner, hub, expect_dx, expect_dy", [
    ("bottom-right", (1890, 1010), -1, -1),    # opens up and to the left
    ("bottom-left", (30, 1010), 1, -1),        # up and right
    ("top-right", (1890, 30), -1, 1),          # down and left
    ("top-left", (30, 30), 1, 1),              # down and right
])
def test_corners_open_away_from_the_edges(corner, hub, expect_dx, expect_dy):
    for n in (1, 3, 5):
        pts, rad = fan(*hub, n, R, SCREEN)
        assert inside(pts), corner
        # EVERY button is up/left of a bottom-right hub (etc.), not just on average
        assert all((x - hub[0]) * expect_dx >= 0 and (y - hub[1]) * expect_dy >= 0 for x, y in pts), (corner, n, pts)


@pytest.mark.parametrize("hub, axis, sign", [
    ((1890, 520), 0, -1),     # right edge: opens left
    ((30, 520), 0, 1),        # left edge: opens right
    ((960, 1010), 1, -1),     # bottom edge (above the taskbar): opens up
    ((960, 30), 1, 1),        # top edge: opens down
])
def test_edges_open_inwards(hub, axis, sign):
    pts, _ = fan(*hub, 3, R, SCREEN)
    assert inside(pts)
    assert all((p[axis] - hub[axis]) * sign >= 0 for p in pts), pts


def test_middle_of_screen_opens_upwards():
    assert away_angle(960, 520, SCREEN) == -90.0
    pts, _ = fan(960, 520, 3, R, SCREEN)
    assert all(y < 520 for _, y in pts)


@pytest.mark.parametrize("n", [1, 2, 3, 5, 8])
def test_buttons_never_overlap_and_stay_on_screen(n):
    for hub in ((30, 30), (1890, 1010), (960, 520), (25, 520)):
        pts, rad = fan(*hub, n, R, SCREEN)
        assert len(pts) == n and inside(pts), (n, hub)
        for i in range(n):
            for j in range(i + 1, n):
                assert math.dist(pts[i], pts[j]) >= 2 * R, (n, hub)
            assert math.dist(pts[i], hub) == pytest.approx(rad, abs=0.01)


def test_second_monitor_coordinates():
    left_monitor = (-1920, 0, 0, 1040)
    pts, _ = fan(-30, 1010, 3, R, left_monitor)       # its bottom-right corner
    assert inside(pts, left_monitor)
    assert all(x <= -30 and y <= 1010 for x, y in pts)


def test_bbox_holds_everything():
    pts, _ = fan(1890, 1010, 3, R, SCREEN)
    l, t, r, b = bbox(pts, R, (1890, 1010), 24)
    for x, y in pts + [(1890, 1010)]:
        assert l <= x - R and x + R <= r and t <= y - R and y + R <= b


def test_hub_dragged_right_into_the_corner_of_a_small_laptop_screen():
    small = (0, 0, 1366, 728)
    for n in range(1, 7):
        pts, _ = fan(1366 - 26, 728 - 26, n, 26, small)
        assert inside(pts, small, 26) and all(x <= 1340 and y <= 702 for x, y in pts), n
