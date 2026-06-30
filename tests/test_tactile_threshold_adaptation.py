from __future__ import annotations

from types import SimpleNamespace

import pytest

from peripersonal_space_toolkit.tactile_threshold_adaptation import AdaptiveTactileThresholdController


def _miss(ledger_id: int, *, is_topup: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        ledger_id=ledger_id,
        trial_uid=f"T{ledger_id:03d}",
        block_number=1,
        trial_number=ledger_id,
        tactile_unix_time=float(ledger_id),
        is_topup=is_topup,
        miss_reason="response_deadline_expired",
    )


def test_adaptive_tactile_threshold_raises_after_every_two_misses() -> None:
    controller = AdaptiveTactileThresholdController(initial_output_34_percent=0.1)

    assert controller.observe_missed_entries([_miss(1)]) == []
    adjustments = controller.observe_missed_entries([_miss(1), _miss(2)])

    assert len(adjustments) == 1
    assert adjustments[0]["old_output_34_percent"] == pytest.approx(0.1)
    assert adjustments[0]["new_output_34_percent"] == pytest.approx(0.11)
    assert controller.summary()["total_misses"] == 2
    assert controller.summary()["misses_since_last_adjustment"] == 0

    second = controller.observe_missed_entries([_miss(1), _miss(2), _miss(3), _miss(4, is_topup=True)])
    assert len(second) == 1
    assert second[0]["new_output_34_percent"] == pytest.approx(0.12)
    assert second[0]["triggering_is_topup"] is True
    assert controller.summary()["adjustment_count"] == 2


def test_adaptive_tactile_threshold_caps_at_output_34_max() -> None:
    controller = AdaptiveTactileThresholdController(initial_output_34_percent=0.495)

    first = controller.observe_missed_entries([_miss(1), _miss(2)])
    second = controller.observe_missed_entries([_miss(1), _miss(2), _miss(3), _miss(4)])

    assert first[0]["new_output_34_percent"] == pytest.approx(0.5)
    assert second == []
    summary = controller.summary()
    assert summary["final_output_34_percent"] == pytest.approx(0.5)
    assert summary["suppressed_at_cap_count"] == 1
    assert summary["capped_at_max"] is True
