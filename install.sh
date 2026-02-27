#!/usr/bin/env bash
# Build & install helper for ocr
# Removes stray desktop.ini files, then installs via uv

set -e
cd "$(dirname "$0")"

echo "Removing desktop.ini files..."
find . -name "desktop.ini" -delete 2>/dev/null || true

echo "Installing ocr (editable)..."
uv tool install --editable .

echo ""
ocr --version
echo "Done."
