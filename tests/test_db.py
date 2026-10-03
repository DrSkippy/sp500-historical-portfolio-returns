import datetime
from decimal import Decimal

import pytest

import returns.db
from returns.db import DB_ENV_VARS, get_db_settings, get_quotes


@pytest.fixture
def db_env(monkeypatch):
    values = {"PGHOST": "db.example", "PGPORT": "5434", "PGUSER": "u", "PGPASSWORD": "p",
              "PGDATABASE": "stock_quotes"}
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    return values


def test_get_db_settings_reads_env(db_env):
    assert get_db_settings() == {"host": "db.example", "port": 5434, "user": "u", "password": "p",
                                 "dbname": "stock_quotes"}


@pytest.mark.parametrize("var", DB_ENV_VARS)
def test_get_db_settings_missing_var_raises(db_env, monkeypatch, var):
    monkeypatch.delenv(var)
    with pytest.raises(RuntimeError, match=var):
        get_db_settings()


def test_get_db_settings_has_no_hardcoded_defaults(monkeypatch):
    for var in DB_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError):
        get_db_settings()


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        self.executed = (sql, params)

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.cur = FakeCursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self.cur


def test_get_quotes_parameterized_and_converts_decimal():
    conn = FakeConnection([(datetime.date(2026, 10, 1), Decimal("660.123456"))])
    rows = get_quotes("SPY", connect=lambda: conn)
    assert rows == [(datetime.date(2026, 10, 1), pytest.approx(660.123456))]
    assert isinstance(rows[0][1], float)
    assert conn.cur.executed[1] == ("SPY", "NASDAQ")
    assert "%s" in conn.cur.executed[0]
