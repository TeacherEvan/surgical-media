"""Tests for layout_solver — offline, deterministic, fast."""

from __future__ import annotations

import pytest
from layout_solver import LayoutBox, SATLayoutSolver


def padded_rect(box: LayoutBox) -> tuple[float, float, float, float]:
    p = max(0.0, box.padding)
    return (box.x0 - p, box.y0 - p, box.x1 + p, box.y1 + p)


def overlaps(a: LayoutBox, b: LayoutBox) -> bool:
    ax0, ay0, ax1, ay1 = padded_rect(a)
    bx0, by0, bx1, by1 = padded_rect(b)
    return min(ax1, bx1) > max(ax0, bx0) and min(ay1, by1) > max(ay0, by0)


def test_non_overlapping_inputs_returned_unchanged():
    boxes = [
        LayoutBox("a", 100.0, 100.0, 200.0, 200.0),
        LayoutBox("b", 400.0, 100.0, 500.0, 200.0),
        LayoutBox("c", 100.0, 400.0, 200.0, 500.0, padding=8.0),
        LayoutBox("locked", 700.0, 300.0, 900.0, 700.0, locked=True),
    ]
    out = SATLayoutSolver.solve(boxes)
    for box in boxes:
        got = out[box.box_id]
        assert (got.x0, got.y0, got.x1, got.y1) == (box.x0, box.y0, box.x1, box.y1)


def test_six_overlapping_cards_vs_locked_center():
    locked = LayoutBox("stage", 860.0, 440.0, 1060.0, 640.0, locked=True)
    cards = [
        LayoutBox(
            f"card-{i}",
            900.0 + i * 15.0,
            500.0 + i * 10.0,
            1050.0 + i * 15.0,
            620.0 + i * 10.0,
            padding=12.0,
        )
        for i in range(6)
    ]
    out = SATLayoutSolver.solve([locked, *cards])
    assert out["stage"].locked
    assert (out["stage"].x0, out["stage"].y0, out["stage"].x1, out["stage"].y1) == (
        locked.x0,
        locked.y0,
        locked.x1,
        locked.y1,
    )
    rects = list(out.values())
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert not overlaps(rects[i], rects[j]), (
                f"{rects[i].box_id} overlaps {rects[j].box_id}"
            )


def test_clamping_far_outside_canvas():
    boxes = [
        LayoutBox("far-right", 5000.0, 100.0, 5300.0, 220.0),
        LayoutBox("far-bottom", 100.0, 4000.0, 320.0, 4150.0),
        LayoutBox("far-topleft", -800.0, -600.0, -500.0, -400.0),
    ]
    out = SATLayoutSolver.solve(boxes, width=1920, height=1080)
    for box in out.values():
        assert box.x0 >= 24.0
        assert box.y0 >= 24.0
        assert box.x1 <= 1920 - 24.0
        assert box.y1 <= 1080 - 24.0


def test_determinism_two_calls_identical():
    boxes = [
        LayoutBox(
            f"b{i}",
            800.0 + i * 30.0,
            450.0 + i * 20.0,
            1000.0 + i * 30.0,
            600.0 + i * 20.0,
            padding=10.0,
        )
        for i in range(8)
    ]
    boxes.append(LayoutBox("hud", 0.0, 0.0, 1920.0, 64.0, locked=True))
    first = SATLayoutSolver.solve(boxes)
    second = SATLayoutSolver.solve(boxes)
    assert list(first) == list(second)
    for key in first:
        a, b = first[key], second[key]
        assert (a.x0, a.y0, a.x1, a.y1) == (b.x0, b.y0, b.x1, b.y1)


def test_empty_list_returns_empty_dict():
    assert SATLayoutSolver.solve([]) == {}


def test_duplicate_ids_raise_value_error():
    boxes = [
        LayoutBox("dup", 0.0, 0.0, 10.0, 10.0),
        LayoutBox("dup", 50.0, 50.0, 60.0, 60.0),
    ]
    with pytest.raises(ValueError, match="dup"):
        SATLayoutSolver.solve(boxes)


def test_locked_smaller_than_forced_overlap_pushes_out():
    locked = LayoutBox("pin", 900.0, 500.0, 1000.0, 580.0, locked=True)
    cards = [
        LayoutBox("c1", 880.0, 480.0, 1020.0, 600.0, padding=16.0),
        LayoutBox("c2", 910.0, 520.0, 1010.0, 560.0, padding=16.0),
        LayoutBox("c3", 850.0, 460.0, 1050.0, 620.0, padding=16.0),
    ]
    out = SATLayoutSolver.solve([locked, *cards])
    locked_out = out["pin"]
    assert (locked_out.x0, locked_out.y0, locked_out.x1, locked_out.y1) == (
        locked.x0,
        locked.y0,
        locked.x1,
        locked.y1,
    )
    for box in cards:
        assert not overlaps(out[box.box_id], locked_out), (
            f"{box.box_id} still overlaps locked rect"
        )


def test_inputs_not_mutated():
    boxes = [
        LayoutBox("a", 100.0, 100.0, 200.0, 200.0),
        LayoutBox("b", 150.0, 120.0, 250.0, 220.0),
    ]
    snapshot = [(b.x0, b.y0, b.x1, b.y1) for b in boxes]
    SATLayoutSolver.solve(boxes)
    assert [(b.x0, b.y0, b.x1, b.y1) for b in boxes] == snapshot


def test_oversized_box_pinned_to_margin():
    box = LayoutBox("huge", -500.0, -500.0, 5000.0, 4000.0)
    out = SATLayoutSolver.solve([box], width=1920, height=1080)
    got = out["huge"]
    assert got.x0 == 24.0
    assert got.y0 == 24.0
    assert got.width == box.width
    assert got.height == box.height
