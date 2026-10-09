import datetime
from decimal import Decimal
from typing import Any, Literal, cast

import psycopg

import pytest

import returns.db
from returns.db import DB_ENV_VARS, get_db_settings, get_quotes
from returns.errors import DatabaseConfigError


@pytest.fixture
def db_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    values = {
        "PGHOST": "db.example",
        "PGPORT": "5434",
        "PGUSER": "u",
        "PGPASSWORD": "p",
        "PGDATABASE": "stock_quotes",
    }
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    return values


def test_get_db_settings_reads_env(db_env: dict[str, str]) -> None:
    assert get_db_settings() == {
        "host": "db.example",
        "port": 5434,
        "user": "u",
        "password": "p",
        "dbname": "stock_quotes",
    }


@pytest.mark.parametrize("var", DB_ENV_VARS)
def test_get_db_settings_missing_var_raises(
    db_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, var: str
) -> None:
    monkeypatch.delenv(var)
    with pytest.raises(DatabaseConfigError, match=var):
        get_db_settings()


def test_get_db_settings_has_no_hardcoded_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var in DB_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(DatabaseConfigError):
        get_db_settings()


def test_get_db_settings_bad_port_raises(
    db_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PGPORT", "fivefourthreefour")
    with pytest.raises(DatabaseConfigError, match="PGPORT"):
        get_db_settings()


class FakeCursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows
        self.executed: tuple[str, tuple[Any, ...]] | None = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc: object) -> Literal[False]:
        return False

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.executed = (sql, params)

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows


class FakeConnection:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.cur = FakeCursor(rows)

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *exc: object) -> Literal[False]:
        return False

    def cursor(self) -> FakeCursor:
        return self.cur


def test_get_quotes_parameterized_and_converts_decimal() -> None:
    conn = FakeConnection([(datetime.date(2026, 10, 1), Decimal("660.123456"))])
    rows = get_quotes(
        "SPY", "NASDAQ", connect=lambda: cast(psycopg.Connection[Any], conn)
    )
    assert len(rows) == 1
    assert rows[0][0] == datetime.date(2026, 10, 1)
    assert rows[0][1] == pytest.approx(660.123456)
    assert isinstance(rows[0][1], float)
    assert conn.cur.executed is not None
    assert conn.cur.executed[1] == ("SPY", "NASDAQ")
    assert "%s" in conn.cur.executed[0]
