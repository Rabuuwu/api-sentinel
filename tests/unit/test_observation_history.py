from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from api_sentinel.freshness import observation
from api_sentinel.metrics import comparable, history_info

END = datetime(2026, 11, 19, tzinfo=UTC)


@pytest.mark.parametrize(('status', 'age', 'freshness', 'effective'), [
    ('UP', 60, 'FRESH', 'UP'),
    ('DOWN', 60, 'FRESH', 'DOWN'),
    ('UP', 151, 'STALE', 'UNKNOWN'),
    ('DOWN', 151, 'STALE', 'UNKNOWN'),
    ('UP', 150, 'FRESH', 'UP'),
    ('UP', -1, 'STALE', 'UNKNOWN'),
    ('UNKNOWN', None, 'AWAITING', 'UNKNOWN'),
    ('PAUSED', 9999, 'PAUSED', 'PAUSED'),
    ('PAUSED', None, 'PAUSED', 'PAUSED'),
])
def test_observation_does_not_modify_record(status, age, freshness, effective):
    monitor = SimpleNamespace(status=status, interval_seconds=60, timeout_seconds=0,
                              last_checked_at=(
                                  END-timedelta(seconds=age) if age is not None else None))
    result = observation(monitor, END)
    assert result['freshness'] == freshness
    assert result['effective_status'] == effective
    assert result['last_observed_status'] == monitor.status == status


def test_limited_history_and_no_data_are_explicit():
    start = END - timedelta(days=30)
    data = history_info({'total': 0}, start, END, 7)
    assert data['retention_limited']
    assert data['first_check_at'] is None
    assert data['completed_checks'] == 0


def test_comparison_requires_retention_boundaries_and_sufficient_samples():
    start = END-timedelta(days=1)
    current = dict(total=1440, first_check_at=start, last_check_at=END)
    previous = dict(total=1440, first_check_at=start-timedelta(days=1), last_check_at=start)
    assert comparable(current, previous, start, END, 7, 60)
    assert not comparable(current, previous, start, END, 1, 60)
    assert not comparable(current, {**previous, 'total': 1}, start, END, 7, 60)
    assert not comparable(current, {**previous, 'first_check_at': start}, start, END, 7, 60)
