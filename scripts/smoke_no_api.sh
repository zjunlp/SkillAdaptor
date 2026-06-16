#!/usr/bin/env bash
# Offline plugin smoke — no API keys, mirrors .github/workflows/smoke.yml
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CORE="$ROOT/skill-adaptor"
WS="$(mktemp -d /tmp/skilladaptor-smoke-XXXXXX)"

echo "=== SkillAdaptor smoke (no API) ==="
cd "$CORE"

python -c "from core.orchestrator import SkillEvolveOrchestrator; from runtime.plugin_host import PluginHost; print('imports_ok')"
python run_plugin.py init --workspace "$WS" --template smoke5
python run_plugin.py --workspace "$WS" --dry-run
python run_plugin.py --manifest "$ROOT/benchmarks/manifests/pinchbench_smoke_5.json" --dry-run
python -m pytest tests/ -q --ignore=tests/integration

echo "=== smoke passed ==="
