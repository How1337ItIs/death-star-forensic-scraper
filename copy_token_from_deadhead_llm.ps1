# Copy GITHUB_TOKEN from deadhead-llm .env to %USERPROFILE%\.github-mcp-token,
# then run create_and_push_repo.ps1. Run from death-star-forensic-scraper folder.
# Sister project: C:\Users\natha\deadhead-llm\deadhead-llm

$ErrorActionPreference = "Stop"
$deadheadEnv = "C:\Users\natha\deadhead-llm\deadhead-llm\.env"
$dest = Join-Path $env:USERPROFILE ".github-mcp-token"

if (-not (Test-Path $deadheadEnv)) {
    Write-Host "Not found: $deadheadEnv"
    Write-Host "Add GITHUB_TOKEN=your_token to that .env (sister project deadhead-llm), then run this again."
    exit 1
}

$line = Get-Content $deadheadEnv -ErrorAction SilentlyContinue | Where-Object { $_ -match '^\s*GITHUB_TOKEN\s*=' }
if (-not $line) {
    Write-Host "GITHUB_TOKEN not set in $deadheadEnv"
    Write-Host "Add one line: GITHUB_TOKEN=your_github_personal_access_token"
    exit 1
}

$val = ($line -replace '^[^=]+=','').Trim()
if ([string]::IsNullOrWhiteSpace($val)) {
    Write-Host "GITHUB_TOKEN is empty in $deadheadEnv"
    exit 1
}

[System.IO.File]::WriteAllText($dest, $val)
Write-Host "Copied GITHUB_TOKEN from deadhead-llm .env to $dest"
& (Join-Path $PSScriptRoot "create_and_push_repo.ps1")
