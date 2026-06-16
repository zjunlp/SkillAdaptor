# Preflight before live PinchBench / matrix smoke (Windows).
# Usage (from repo root):
#   . scripts\load_secrets.ps1
#   . scripts\verify_env.ps1

$ErrorActionPreference = "Continue"

Write-Host "=== SkillAdaptor verify_env ===" -ForegroundColor Cyan

if (-not $env:OPENAI_API_KEY) {
    $load = Join-Path $PSScriptRoot "load_secrets.ps1"
    if (Test-Path $load) { . $load }
}

$npm = Join-Path $env:USERPROFILE "AppData\Roaming\npm"
if (Test-Path $npm) { $env:Path = "$npm;" + $env:Path }

$fail = 0

$oc = Get-Command openclaw -ErrorAction SilentlyContinue
if ($oc) {
    Write-Host "OK openclaw -> $($oc.Source)" -ForegroundColor Green
    openclaw --version 2>&1 | Select-Object -First 1 | ForEach-Object { Write-Host "    $_" }
} else {
    Write-Host "FAIL openclaw not on PATH (npm install -g openclaw)" -ForegroundColor Red
    $fail++
}

if ($oc) {
    $gw = openclaw gateway status 2>&1 | Out-String
    if ($gw -match "Connectivity probe: ok|Reachable: yes") {
        Write-Host "OK OpenClaw gateway reachable" -ForegroundColor Green
    } else {
        Write-Host "FAIL OpenClaw gateway — run: openclaw gateway start" -ForegroundColor Red
        $fail++
    }
}

foreach ($key in @("PINCHBENCH_PATH", "OPENAI_API_KEY", "SkillEvolve_EMBEDDING_API_KEY")) {
    if ([string]::IsNullOrWhiteSpace((Get-Item -Path "Env:$key" -ErrorAction SilentlyContinue).Value)) {
        Write-Host "FAIL $key unset" -ForegroundColor Red
        $fail++
    } else {
        Write-Host "OK $key" -ForegroundColor Green
    }
}

if ($env:PINCHBENCH_PATH -and -not (Test-Path $env:PINCHBENCH_PATH)) {
    Write-Host "FAIL PINCHBENCH_PATH not found: $env:PINCHBENCH_PATH" -ForegroundColor Red
    $fail++
}

Write-Host ""
if ($fail -eq 0) {
    Write-Host "Ready for live run." -ForegroundColor Green
} else {
    Write-Host "$fail check(s) failed — fix before --live." -ForegroundColor Yellow
    exit 1
}
