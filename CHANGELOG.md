# Changelog

All notable changes to the OCR tool will be documented in this file.

## [v0.10.0] - 2026-03-19

### Bug Fixes
- **Timestamp preservation**: File modification dates are now preserved when renaming files (`--rename`)
- **Watch mode stability**: Fixed `asyncio.create_task` RuntimeError when processing files from watchdog's background thread (uses `run_coroutine_threadsafe` now)
- **Watch mode duplication**: Renamed files no longer trigger re-processing loops that created `_2`, `_3` suffixed copies
- **Skip images in rename flow**: `--rename` and `--dry-run` no longer download/extract images unnecessarily, reducing API costs and disk I/O
- **Page keywords**: `--pages all`, `--pages *`, `--pages pg1`, and `--pages first` now work as explicit page selectors

### Added
- Test suite with pytest (page parser, file renamer, cache manager, output manager, folder watcher, CLI)
- CI/CD with GitHub Actions (lint, test on Linux/Windows/macOS)
- Release workflow with PyPI publishing and GitHub Releases
- Cross-platform executable builds (Windows, macOS, Linux) via PyInstaller
- `CHANGELOG.md`, `CONTRIBUTING.md`, issue and PR templates

### Changed
- Dev dependencies now include pytest, pytest-asyncio, pytest-cov, ruff
- PyInstaller-compatible prompt file loading in filename generator

## [v0.9.1]

- Bug fixes and improvements

## [v0.9.0]

- Extract filename prompt to `.md` file, add `install.sh`

## [v0.8.0]

- Return `pages_processed` from `process_file`, default page headlines on

## [v0.7.0]

- Enhanced output formatting with `--verbose` mode
- Configurable confidence threshold (`--confidence`)
- Filename-based metadata extraction

## [v0.6.0]

- Image descriptions enabled by default
- Rename confirmation
- File concatenation with `--concat`

## [v0.5.0]

- AI-powered image descriptions

## [v0.4.0]

- Numeric confidence scoring (0.0-1.0)

## [v0.3.0]

- Unified CLI command (removed subcommands)

## [v0.2.2]

- `.ocr` subdirectory structure
- Page-based naming (`.pg1.md` vs `.md`)

## [v0.2.0]

- Intelligent filename generation
- YAML frontmatter metadata
- Smart caching

## [v0.1.0]

- Initial release with basic OCR functionality
