#!/usr/bin/env bash
# Load gitignored secrets into the current shell.
# Usage:  source scripts/load_secrets.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOADED=0

for env_file in "$ROOT/secrets/.env" "$ROOT/skill-adaptor/secrets/.env"; do
  if [[ -f "$env_file" ]]; then
    echo "Loading secrets from $env_file"
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
    LOADED=1
    break
  fi
done

if [[ "$LOADED" -eq 0 ]]; then
  echo "No secrets/.env found."
  echo "  cp .env.example secrets/.env"
  echo "  Edit API keys and benchmark paths, then re-run: source scripts/load_secrets.sh"
fi

export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
