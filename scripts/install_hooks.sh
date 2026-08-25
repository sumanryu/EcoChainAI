#!/usr/bin/env bash
# Run once after cloning: bash scripts/install_hooks.sh
set -eu

HOOK_DIR="$(git rev-parse --git-dir)/hooks"
cp scripts/pre-commit-secret-check.sh "$HOOK_DIR/pre-commit"
chmod +x "$HOOK_DIR/pre-commit"
echo "Pre-commit secret-scan hook installed."
