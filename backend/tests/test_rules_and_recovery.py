import pytest

from app.core.errors import InvalidTransition, RuleViolation
from app.core.rules import (BLOOD_GROUPS, CANDIDATE_TRANSITIONS, REQUEST_TRANSITIONS, match_blood,
                            validate_candidate_transition, validate_request_transition)
from app.services.recovery import plan_candidate_event


def test_exact_match_for_every_group_and_component():
    for g in BLOOD_GROUPS:
        for comp in ("Whole Blood", "Packed Red Cells", "Platelets", "Plasma"):
            assert match_blood(g, g, comp).level == "exact"


def test_red_cell_compatibility_is_conservative():
    assert match_blood("A+", "O-", "Packed Red Cells").level == "compatible"
    assert match_blood("O+", "A+", "Packed Red Cells").level == "none"
    assert match_blood("O-", "O+", "Packed Red Cells").level == "none"
    assert match_blood("AB+", "B-", "Packed Red Cells").level == "compatible"


def test_whole_blood_and_platelets_need_identical_group():
    assert match_blood("O+", "O-", "Whole Blood").level == "none"
    assert match_blood("A+", "A-", "Platelets").level == "none"


def test_plasma_uses_abo_only():
    assert match_blood("A+", "AB+", "Plasma").level == "compatible"
    assert match_blood("AB+", "O+", "Plasma").level == "none"


def test_unknown_inputs_never_match():
    assert match_blood("X+", "O+", "Plasma").level == "none"
    assert match_blood("O+", "O+", "Unicorn").level == "none"


def test_request_transitions_allowed_and_rejected():
    validate_request_transition("open", "under_review")
    validate_request_transition("awaiting_confirmation", "fulfilled")
    with pytest.raises(InvalidTransition):
        validate_request_transition("open", "fulfilled")
    with pytest.raises(InvalidTransition):
        validate_request_transition("fulfilled", "open")
    with pytest.raises(InvalidTransition):
        validate_request_transition("open", "open")
    assert REQUEST_TRANSITIONS["fulfilled"] == set() and REQUEST_TRANSITIONS["cancelled"] == set()


def test_invalid_request_transition_message_lists_allowed_states():
    try:
        validate_request_transition("open", "fulfilled")
    except InvalidTransition as exc:
        assert "under_review" in exc.message
    else:
        raise AssertionError("expected InvalidTransition")


def test_candidate_transitions():
    validate_candidate_transition("reported_available", "declined")
    with pytest.raises(InvalidTransition):
        validate_candidate_transition("reported_available", "confirmed_available")
    assert CANDIDATE_TRANSITIONS["declined"] == {"awaiting_confirmation"}


def test_failure_events_plan_the_right_states():
    assert plan_candidate_event("STOCK_UNAVAILABLE", "blood_bank", "reported_available", None).new_status == "unavailable"
    assert plan_candidate_event("DONOR_DECLINED", "donor", "reported_available", None).new_status == "declined"
    assert plan_candidate_event("DONOR_NO_RESPONSE", "donor", "reported_available", None).new_status == "no_response"
    assert plan_candidate_event("DATA_STALE", "donor", "reported_available", None).new_status == "stale"


def test_failure_events_are_marked_as_simulation():
    assert plan_candidate_event("DONOR_DECLINED", "donor", "reported_available", None).simulated is True
    assert plan_candidate_event("SELECT_FOR_REVIEW", "donor", "reported_available", None).simulated is False


def test_event_type_must_match_candidate_type():
    with pytest.raises(RuleViolation):
        plan_candidate_event("STOCK_UNAVAILABLE", "donor", "reported_available", None)
    with pytest.raises(RuleViolation):
        plan_candidate_event("DONOR_DECLINED", "blood_bank", "reported_available", None)
    with pytest.raises(RuleViolation):
        plan_candidate_event("NOPE", "donor", "reported_available", None)


def test_declined_and_unavailable_can_only_return_through_reinstatement():
    for state in ("declined", "unavailable"):
        with pytest.raises(InvalidTransition):
            plan_candidate_event("SELECT_FOR_REVIEW", "donor", state, None)
        with pytest.raises(InvalidTransition):
            plan_candidate_event("DATA_STALE", "donor", state, None)
        with pytest.raises(RuleViolation):
            plan_candidate_event("REINSTATE_CANDIDATE", "donor", state, "")
        plan = plan_candidate_event("REINSTATE_CANDIDATE", "donor", state, "Donor called back to say yes")
        assert plan.new_status == "awaiting_confirmation"


def test_repeating_the_same_event_is_rejected():
    with pytest.raises(InvalidTransition):
        plan_candidate_event("DONOR_DECLINED", "donor", "declined", None)


def test_source_confirmed_option_can_still_be_selected_for_review():
    plan = plan_candidate_event("SELECT_FOR_REVIEW", "blood_bank", "confirmed_available", None, "BB-001")
    assert plan.new_status == "awaiting_confirmation"
    assert "BB-001" in plan.reason
