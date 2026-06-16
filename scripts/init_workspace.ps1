# Initialize SkillAdaptor plugin workspace (smoke5 template = verified smoke5_v02 task set)
param(
    [string]$Workspace = (Join-Path $PSScriptRoot "..\plugin\workspace"),
    [string]$Template = "smoke5",
    [ValidateSet("bundled", "auto_discover", "folders")]
    [string]$Mode = "bundled"
)

$SkillAdaptorRoot = Join-Path $PSScriptRoot "..\skill-adaptor"
Push-Location $SkillAdaptorRoot
try {
    python run_plugin.py init `
        --workspace $Workspace `
        --template $Template `
        --mode $Mode `
        --harness openclaw `
        --benchmark pinchbench
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "`nDry-run:"
    python run_plugin.py --workspace $Workspace --dry-run
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
