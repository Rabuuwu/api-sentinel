from api_sentinel.domain import Transition, transition


def test_three_failures_open_one_incident_and_two_successes_recover():
    state = Transition("UNKNOWN", 0, 0)
    events = []
    for success in [False, False, False, False, True, True, True]:
        state = transition(state.status, state.failures, state.successes, success, 3, 2)
        if state.event:
            events.append(state.event)
    assert events == ["INCIDENT_OPENED", "INCIDENT_RESOLVED"]
    assert state.status == "UP"


def test_intermittent_results_reset_consecutive_counts():
    state = Transition("UP", 0, 0)
    for success in [False, False, True, False, False, True]:
        state = transition(state.status, state.failures, state.successes, success, 3, 2)
        assert state.event is None
        assert state.status == "UP"


def test_failed_recovery_resets_success_streak():
    state = transition("DOWN", 3, 0, True, 3, 2)
    assert state.status == "DOWN"
    state = transition(state.status, state.failures, state.successes, False, 3, 2)
    assert state.successes == 0
    assert transition(state.status, state.failures, state.successes, True, 3, 2).status == "DOWN"


def test_paused_ignores_results():
    assert transition("PAUSED", 0, 0, False, 1, 1) == Transition("PAUSED", 0, 0)


def test_first_success_is_up():
    assert transition("UNKNOWN", 0, 0, True, 3, 2).status == "UP"
