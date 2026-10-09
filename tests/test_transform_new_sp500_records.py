import io
import sys

import pytest

from tests.conftest import load_bin_module

transform = load_bin_module("transform_new_sp500_records")

PASTED = [
    "Mar. 11, 2026\n",
    "6,790.09\t6,811.15\t6,745.59\t6,775.80\n",
    "2,909,570,674\n",
]
EXPECTED = (
    "Mar 11, 2026\t6,790.09\t6,811.15\t6,745.59\t6,775.80\t6,775.80\t2,909,570,674"
)


def test_record_becomes_an_sp500_tab_line() -> None:
    assert list(transform.transform_records(PASTED)) == [EXPECTED]


def test_output_parses_like_sp500_tab() -> None:
    fields = EXPECTED.split("\t")
    assert len(fields) == 7  # Date Open High Low Close* "Adj Close**" Volume
    assert fields[4] == fields[5]


def test_incomplete_trailing_record_is_dropped_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    lines = PASTED * 2 + ["Mar. 09, 2026\n"]
    assert list(transform.transform_records(lines)) == [EXPECTED, EXPECTED]
    assert "Ignoring 1 trailing line(s)" in caplog.text


def test_main_writes_lines_to_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("".join(PASTED)))
    transform.main()
    assert capsys.readouterr().out == EXPECTED + "\n"
