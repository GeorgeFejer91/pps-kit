from __future__ import annotations

import math

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
