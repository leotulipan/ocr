"""Tests for CLI interface."""

import re

from typer.testing import CliRunner

from ocr.main import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


class TestCLI:
    """Tests for CLI commands."""

    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "OCR version" in result.output

    def test_help_flag(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "OCR CLI" in result.output

    def test_run_help(self):
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "--rename" in output
        assert "--dry-run" in output
        assert "--pages" in output
        assert "--confidence" in output

    def test_watch_help(self):
        result = runner.invoke(app, ["watch", "--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "--rename" in output
        assert "--recursive" in output

    def test_run_nonexistent_file(self):
        result = runner.invoke(app, ["run", "nonexistent_file.pdf"])
        assert result.exit_code != 0
