# Load gitignored secrets into the current PowerShell session.
# Usage (from repo root):  . scripts\load_secrets.ps1

$root = if ($PSScriptRoot -match 'scripts$') {
    Split-Path $PSScriptRoot -Parent
} else {
    $PSScriptRoot
}

$candidates = @(
    (Join-Path $root "secrets\.env"),
    (Join-Path $root "skill-adaptor\secrets\.env")
)

$loaded = $false
foreach ($envFile in $candidates) {
    if (Test-Path $envFile) {
        Write-Host "Loading secrets from $envFile" -ForegroundColor Cyan
        Get-Content $envFile | ForEach-Object {
            if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
                $k = $matches[1].Trim()
                $v = $matches[2].Trim()
                [System.Environment]::SetEnvironmentVariable($k, $v, 'Process')
            }
        }
        $loaded = $true
        break
    }
}

if (-not $loaded) {
    Write-Host "No secrets/.env found." -ForegroundColor Yellow
    Write-Host "  Copy:  .env.example  ->  secrets\.env" -ForegroundColor Yellow
    Write-Host "  Then fill in API keys and benchmark paths." -ForegroundColor Yellow
}

# OpenClaw / Claude Code global npm shims (required for PinchBench live runs)
$npm = Join-Path $env:USERPROFILE "AppData\Roaming\npm"
if (Test-Path $npm) {
    if ($env:Path -notlike "*$npm*") {
        $env:Path = "$npm;" + $env:Path
    }
}

$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
