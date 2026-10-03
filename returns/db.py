"""PostgreSQL access for recent quote data.

Connection settings come from the standard libpq environment variables, which are
set in `.envrc` and loaded by direnv (see `.envrc.example`):

    PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE
"""

import datetime
import os
from typing import Any, Callable

import psycopg

DB_ENV_VARS = ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE")


def get_db_settings() -> dict[str, Any]:
    """
    Read database connection settings from the environment.

    Returns:
    dict: psycopg connection kwargs (host, port, user, password, dbname).

    Raises:
    RuntimeError: if any required variable is unset; there are no defaults.
    """
    missing = [v for v in DB_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise RuntimeError(
            f"Missing database environment variables: {', '.join(missing)}. "
            "Set them in .envrc (see .envrc.example) and run `direnv allow`."
        )
    return {
        "host": os.environ["PGHOST"],
        "port": int(os.environ["PGPORT"]),
        "user": os.environ["PGUSER"],
        "password": os.environ["PGPASSWORD"],
        "dbname": os.environ["PGDATABASE"],
    }


def get_connection() -> psycopg.Connection[Any]:
    """Open a psycopg connection using settings from the environment."""
    return psycopg.connect(**get_db_settings())


def get_quotes(
    symbol: str,
    namespace: str = "NASDAQ",
    connect: Callable[[], psycopg.Connection[Any]] = get_connection,
) -> list[tuple[datetime.date, float]]:
    """
    Query closing prices for a symbol from the quotes table, sorted ascending by date.

    Parameters:
    symbol (str): Ticker symbol, e.g. "SPY".
    namespace (str): Quote namespace in the quotes table.
    connect (callable): Connection factory (injectable for tests).

    Returns:
    list: (date, close) tuples with close as float.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT date, close FROM quotes WHERE symbol = %s AND namespace = %s ORDER BY date ASC",
            (symbol, namespace),
        )
        rows = cur.fetchall()
    return [(d, float(close)) for d, close in rows]
