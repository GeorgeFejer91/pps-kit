from __future__ import annotations

from peripersonal_space_toolkit.dashboard_app import (
    _custom_project_design_from_source,
    _earliest_changed_design_segment,
    _is_readonly_profile_design,
)
from peripersonal_space_toolkit.design import default_design
from peripersonal_space_toolkit.participant_orders import SEEDED_FACTORADIC_CYCLE


def test_copy_to_edit_name_contains_immutable_source_id() -> None:
    source = default_design()
    source.study_profile_id = "study_unique_007"
    source.study_profile_title = "Published profile"
    custom = _custom_project_design_from_source(source, project_name="My adaptation")
    assert custom.name == "My adaptation [study_unique_007]"
    assert custom.study_profile_reference_parameters["profile_status"] == "draft"
    assert custom.study_profile_reference_parameters["customized_from_profile_id"] == "study_unique_007"
    assert custom.protocol.participant_order_policy["algorithm"] == SEEDED_FACTORADIC_CYCLE
    assert not _is_readonly_profile_design(custom)


def test_finalized_custom_profile_is_copy_to_edit_only() -> None:
    custom = _custom_project_design_from_source(default_design(), project_name="Finished")
    custom.study_profile_reference_parameters["profile_status"] = "finalized"
    assert _is_readonly_profile_design(custom)


def test_changed_decision_identifies_earliest_downstream_invalidation_boundary() -> None:
    original = default_design()
    changed = _custom_project_design_from_source(original, project_name="Changed")
    baseline = _custom_project_design_from_source(original, project_name="Changed")
    assert _earliest_changed_design_segment(baseline, changed) is None
    changed.protocol.soa_values_ms = [123, 456]
    assert _earliest_changed_design_segment(baseline, changed) == 3
    changed.trajectory.end_radius_m = changed.trajectory.end_radius_m + 0.1
    assert _earliest_changed_design_segment(baseline, changed) == 1
