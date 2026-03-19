"""Tests for CLI interface."""

from typer.testing import CliRunner

from ocr.main import app

runner = CliRunner()


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
        assert "--rename" in result.output
        assert "--dry-run" in result.output
        assert "--pages" in result.output
        assert "--confidence" in result.output

    def test_watch_help(self):
        result = runner.invoke(app, ["watch", "--help"])
        assert result.exit_code == 0
        assert "--rename" in result.output
        assert "--recursive" in result.output

    def test_run_nonexistent_file(self):
        result = runner.invoke(app, ["run", "nonexistent_file.pdf"])
        assert result.exit_code != 0
