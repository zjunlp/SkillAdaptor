#!/usr/bin/env bash
# Pre-push sanity check — run before first git push.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
FAIL=0

fail() { echo "FAIL $*"; FAIL=1; }
ok() { echo "OK  $*"; }

echo "=== SkillAdaptor verify_before_push ==="

for rel in secrets/.env skill-adaptor/secrets/.env; do
  if [[ -f "$rel" ]]; then
    if git check-ignore -q "$rel" 2>/dev/null; then ok "$rel is gitignored"; else fail "$rel is NOT gitignored"; fi
    if git ls-files --error-unmatch "$rel" >/dev/null 2>&1; then fail "$rel is tracked"; fi
  fi
done

for prefix in docs/ secrets/ plugin/workspace/ plugin/workspace_bench/ assets/ skill-adaptor/scripts/ CHANGELOG.md VERSION.md; do
  if git ls-files "$prefix" 2>/dev/null | grep -q .; then fail "tracked under $prefix"; else ok "nothing tracked under $prefix"; fi
done

if git grep -E 'sk-[a-zA-Z0-9]{20,}' -- ':!*.example' ':!secrets/*' 2>/dev/null; then
  fail "sk-... in tracked files"
else
  ok "no sk-... keys in tracked files"
fi

if git grep -E 'http://(35|34)\.[0-9]+\.' 2>/dev/null; then
  fail "private relay IP in tracked files"
else
  ok "no private relay IPs"
fi

for req in README.md LICENSE .env.example skill-adaptor/run_plugin.py scripts/load_secrets.ps1 paper/skilladaptor.pdf; do
  [[ -f "$req" ]] && ok "present: $req" || fail "missing: $req"
done

if [[ "$FAIL" -eq 0 ]]; then
  echo "=== All checks passed ==="
else
  echo "=== Fix issues before push ==="
  exit 1
fi
