"""services/locateanything/model.py — LocateAnythingBackend._parse().

`_parse` only touches `self` (no loaded weights needed), so we instantiate the
backend WITHOUT calling `.load()` (which would require torch/transformers) and
exercise the pure token-parsing logic directly.
"""

from __future__ import annotations

from services.locateanything.model import LocateAnythingBackend
from services.shared.config import Settings


def _backend() -> LocateAnythingBackend:
    # Settings() has no side effects and .load() is never called, so the
    # heavy `transformers`/`torch` imports inside .load() are never reached.
    return LocateAnythingBackend(Settings())


def test_parse_box_token_is_not_misread_as_two_points():
    backend = _backend()
    answer = "<box><100><200><300><400></box>"

    locations = backend._parse(answer, w=1000, h=1000, label="bolt", top_k=10)

    assert len(locations) == 1
    loc = locations[0]
    assert loc.box is not None
    assert (loc.box.x1, loc.box.y1, loc.box.x2, loc.box.y2) == (100.0, 200.0, 300.0, 400.0)
    # Point should be the box centroid, not one of the 4 raw ints misread as xy.
    assert loc.point.x == (100.0 + 300.0) / 2
    assert loc.point.y == (200.0 + 400.0) / 2


def test_parse_bare_point_token_has_no_box():
    backend = _backend()
    answer = "<box><500><600></box>"

    locations = backend._parse(answer, w=1000, h=1000, label="bolt", top_k=10)

    assert len(locations) == 1
    loc = locations[0]
    assert loc.box is None
    assert loc.point.x == 500.0
    assert loc.point.y == 600.0


def test_parse_mixed_boxes_and_points_in_one_answer():
    backend = _backend()
    answer = (
        "<box><100><100><200><200></box> some text "
        "<box><300><400></box>"
    )

    locations = backend._parse(answer, w=1000, h=1000, label="bolt", top_k=10)

    assert len(locations) == 2
    assert locations[0].box is not None  # box came first
    assert locations[1].box is None  # bare point second


def test_parse_top_k_truncates_results():
    backend = _backend()
    answer = "".join(f"<box><{i}><{i}></box>" for i in range(5))

    locations = backend._parse(answer, w=1000, h=1000, label="bolt", top_k=2)

    assert len(locations) == 2


def test_parse_rank_based_scores_are_descending_and_first_is_one():
    backend = _backend()
    answer = "".join(f"<box><{i}><{i}></box>" for i in range(4))

    locations = backend._parse(answer, w=1000, h=1000, label="bolt", top_k=10)
    scores = [loc.score for loc in locations]

    assert scores[0] == 1.0
    assert scores == sorted(scores, reverse=True)
    assert len(set(scores)) == len(scores)  # strictly descending, no ties


def test_parse_single_result_gets_score_one():
    backend = _backend()
    answer = "<box><1><2></box>"

    locations = backend._parse(answer, w=1000, h=1000, label="bolt", top_k=10)

    assert locations[0].score == 1.0


def test_parse_normalizes_from_1000_scale_to_pixel_coordinates():
    backend = _backend()
    answer = "<box><500><500><1000><1000></box>"

    locations = backend._parse(answer, w=800, h=400, label="bolt", top_k=10)
    box = locations[0].box

    assert box.x1 == 500 / 1000 * 800
    assert box.y1 == 500 / 1000 * 400
    assert box.x2 == 800  # 1000/1000 * 800
    assert box.y2 == 400  # 1000/1000 * 400


def test_parse_no_tokens_returns_empty_list():
    backend = _backend()

    locations = backend._parse("no location tokens here", w=100, h=100, label="bolt", top_k=10)

    assert locations == []


def test_parse_label_is_propagated_to_every_location():
    backend = _backend()
    answer = "<box><1><1><2><2></box><box><3><3></box>"

    locations = backend._parse(answer, w=100, h=100, label="the widget", top_k=10)

    assert all(loc.label == "the widget" for loc in locations)
