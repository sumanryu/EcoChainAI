#!/usr/bin/env bash
# Pre-commit hook: block commits containing AWS access keys / secrets.
# Install: bash scripts/install_hooks.sh   (run once per clone)

set -eu

PATTERNS='AKIA[0-9A-Z]{16}|aws_secret_access_key\s*[:=]\s*[A-Za-z0-9/+=]{20,}|-----BEGIN (RSA |EC )?PRIVATE KEY-----'

staged=$(git diff --cached --name-only --diff-filter=ACM)

if [ -z "$staged" ]; then
  exit 0
fi

found=0
for f in $staged; do
  # skip binary files and this hook itself
  if [ -f "$f" ] && ! file "$f" | grep -q binary; then
    if grep -Ein "$PATTERNS" "$f" > /dev/null 2>&1; then
      echo "BLOCKED: possible AWS credential found in $f"
      grep -Ein "$PATTERNS" "$f" | head -3
      found=1
    fi
  fi
done

if [ "$found" -eq 1 ]; then
  echo ""
  echo "Commit blocked. Remove the secret, or if this is a false positive,"
  echo "commit with --no-verify (only if you are certain)."
  exit 1
fi

exit 0