from datetime import UTC, datetime

from app.core.db import as_utc


def test_naive_sqlite_datetime_compares_with_utcnow():
    naive = datetime(2026, 10, 1, 14, 13, 6)
    now = datetime(2026, 10, 1, 14, 14, 6, tzinfo=UTC)
    aware = as_utc(naive)
    assert aware is not None
    assert aware < now
    assert (aware > now) is False
