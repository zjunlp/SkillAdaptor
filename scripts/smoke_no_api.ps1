# Offline plugin smoke — no API keys, mirrors .github/workflows/smoke.yml
# Usage: .\scripts\smoke_no_api.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$core = Join-Path $root "skill-adaptor"
$ws = Join-Path $env:TEMP "skilladaptor-smoke-$([guid]::NewGuid().ToString('N').Substring(0,8))"
$stub = Join-Path $root "benchmarks\generic_stubs\task_generic_shell_safe.md"

Write-Host "=== SkillAdaptor smoke (no API) ===" -ForegroundColor Cyan
Set-Location $core

python -c "from core.orchestrator import SkillEvolveOrchestrator; from core.provider_config import resolve_provider; from runtime.plugin_host import PluginHost; print('imports_ok')"
python run_plugin.py init --workspace $ws
New-Item -ItemType Directory -Force -Path (Join-Path $ws "input_task") | Out-Null
Copy-Item $stub (Join-Path $ws "input_task\task_generic_shell_safe.md")
python run_plugin.py --workspace $ws --dry-run

$batch1 = @(
    "tests/test_adapter_hints.py",
    "tests/test_embedding_config.py",
    "tests/test_evolution_guard.py",
    "tests/test_harness.py",
    "tests/test_llm_json.py",
    "tests/test_llm_retry.py",
    "tests/test_manifest_guard.py",
    "tests/test_openclaw_cli.py",
    "tests/test_program_registry.py",
    "tests/test_retrieval_validation_freeze.py",
    "tests/test_reviser_revise.py",
    "tests/test_skill_export.py"
)
$batch2 = @(
    "tests/test_skill_matcher_strict.py",
    "tests/test_skill_retrieval.py",
    "tests/test_skill_writer.py",
    "tests/test_task_context.py",
    "tests/test_task_domain.py",
    "tests/test_task_workspace.py",
    "tests/test_trajectory_step_merge.py",
    "tests/test_validator_adoption.py",
    "tests/test_webshop_per_task.py",
    "tests/test_workspace_lock.py"
)
python -m pytest @batch1 -q
python -m pytest @batch2 -q

Write-Host "=== smoke passed ===" -ForegroundColor Green
