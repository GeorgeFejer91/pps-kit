from __future__ import annotations

import math
from pathlib import Path

import pytest

from peripersonal_space_toolkit.participant_orders import (
    SEEDED_FACTORADIC_CYCLE,
    default_order_policy,
    participant_order,
    seeded_factoradic_order,
)


def test_factoradic_cycle_is_unique_and_reproducible() -> None:
    blocks = ["A", "B", "C", "D"]
    first = [seeded_factoradic_order(blocks, participant_index=index, seed=47) for index in range(1, 25)]
    second = [seeded_factoradic_order(blocks, participant_index=index, seed=47) for index in range(1, 25)]
    assert len({item.block_order for item in first}) == math.factorial(len(blocks))
    assert first == second
    assert {item.cycle_index for item in first} == {0}


def test_factoradic_cycle_rolls_over_with_cycle_identity() -> None:
    blocks = ["A", "B", "C"]
    item = seeded_factoradic_order(blocks, participant_index=7, seed=9)
    assert item.cycle_index == 1
    assert sorted(item.block_order) == blocks


def test_factoradic_rejects_duplicate_blocks_and_bad_indices() -> None:
    with pytest.raises(ValueError, match="unique"):
        seeded_factoradic_order(["A", "A"], participant_index=1, seed=1)
    with pytest.raises(ValueError, match="at least 1"):
        seeded_factoradic_order(["A"], participant_index=0, seed=1)


def test_legacy_order_algorithms_remain_available() -> None:
    fixed = participant_order(["A", "B"], participant_index=8, legacy_algorithm="fixed")
    assert fixed.block_order == ("A", "B")
    policy = default_order_policy(seed=42)
    assert policy["algorithm"] == SEEDED_FACTORADIC_CYCLE

def test_teneggi_keeps_each_social_condition_together_in_runner_order() -> None:
    from peripersonal_space_toolkit.dashboard_app import _run_setup_preview_rows
    from peripersonal_space_toolkit.design import block_trial_rows, participant_block_orders
    from peripersonal_space_toolkit.templates import load_template

    root = Path(__file__).resolve().parents[3]
    design = load_template(
        root / "packages/pps-resources/study_templates/teneggi_2013_social_face_pps.json"
    ).design
    labels = [spec.label for spec in design.protocol.block_specs]
    pool = block_trial_rows(design)
    blocks = [
        {"block_label": label, "trial_count": sum(row["block_label"] == label for row in pool)}
        for label in labels
    ]
    assert [block["trial_count"] for block in blocks] == [52] * 4
    _, schedule = _run_setup_preview_rows(
        blocks,
        participant_count=18,
        structure="single",
        seed=design.protocol.random_seed,
        order_policy=design.protocol.participant_order_policy,
    )
    planned = participant_block_orders(design)
    for participant, order in planned.items():
        assert order == [row["block_label"] for row in schedule if row["participant_id"] == participant]
    orders = list(planned.values())
    assert orders.count(labels) == orders.count(labels[2:] + labels[:2]) == 9

    broken_policy = {**design.protocol.participant_order_policy, "block_groups": [labels[:2]]}
    with pytest.raises(ValueError, match="each block exactly once"):
        participant_order(labels, participant_index=1, policy=broken_policy)
