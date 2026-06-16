# Pre-push sanity check — run before first git push.
# Usage:  .\scripts\verify_before_push.ps1

$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$fail = 0

Write-Host "=== SkillAdaptor verify_before_push ===" -ForegroundColor Cyan

function Fail($msg) {
    Write-Host "FAIL $msg" -ForegroundColor Red
    $script:fail++
}

function Ok($msg) {
    Write-Host "OK  $msg" -ForegroundColor Green
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "git not installed — cannot verify tracked files"
} else {
    if (-not (Test-Path (Join-Path $root ".git"))) {
        Write-Host "WARN no .git yet — run: git init" -ForegroundColor Yellow
    }
}

# --- secrets must never be tracked ---
$secretPaths = @(
    "secrets\.env",
    "skill-adaptor\secrets\.env"
)
foreach ($rel in $secretPaths) {
    $full = Join-Path $root $rel
    if (Test-Path $full) {
        $gi = git check-ignore -v $rel 2>$null
        if ($gi) { Ok "$rel is gitignored" } else { Fail "$rel is NOT gitignored" }
        git ls-files --error-unmatch $rel 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { Fail "$rel is tracked by git" }
    }
}

# --- blocked paths must not appear in git index ---
$blockedPrefixes = @(
    "docs/",
    "secrets/",
    "plugin/workspace/",
    "plugin/workspace_bench/",
    "plugin/workspace_matrix/",
    "plugin/workspace_live_test/",
    "plugin/workspace_test_init/",
    "assets/",
    "skill-adaptor/scripts/",
    "CHANGELOG.md",
    "VERSION.md"
)
foreach ($prefix in $blockedPrefixes) {
    $files = git ls-files $prefix 2>$null
    if ($files) { Fail "tracked files under $prefix" }
    else { Ok "nothing tracked under $prefix" }
}

# --- no real API keys in tracked files ---
$keyHits = git grep -E "sk-[a-zA-Z0-9]{20,}" -- ":!*.example" ":!secrets/*" ":!.gitignore" 2>$null
if ($keyHits) {
    Fail "sk-... pattern in tracked files"
    Write-Host $keyHits
} else {
    Ok "no sk-... keys in tracked files"
}

# --- no private relay IPs in tracked files ---
$ipHits = git grep -E "http://(35|34)\.[0-9]+\." 2>$null
if ($ipHits) {
    Fail "private relay IP in tracked files"
    Write-Host $ipHits
} else {
    Ok "no private relay IPs in tracked files"
}

# --- .env.example must be placeholders only ---
$example = Join-Path $root ".env.example"
if (Test-Path $example) {
    $ex = Get-Content $example -Raw
    if ($ex -match "sk-[a-zA-Z0-9]{20,}") { Fail ".env.example contains real-looking key" }
    elseif ($ex -match "http://(35|34)\.[0-9]+") { Fail ".env.example contains private IP URL" }
    else { Ok ".env.example uses placeholders only" }
}

# --- required public files ---
foreach ($req in @("README.md", "LICENSE", ".env.example", "skill-adaptor/run_plugin.py", "scripts/load_secrets.ps1", "paper/skilladaptor.pdf")) {
    if (Test-Path (Join-Path $root $req)) { Ok "present: $req" }
    else { Fail "missing required: $req" }
}

if ($fail -eq 0) {
    Write-Host "`n=== All checks passed — safe to git add / push ===" -ForegroundColor Green
    Write-Host "Recommended: git add -A && git status   (review list before commit)" -ForegroundColor Cyan
} else {
    Write-Host "`n=== $fail issue(s) — fix before push ===" -ForegroundColor Red
    exit 1
}
