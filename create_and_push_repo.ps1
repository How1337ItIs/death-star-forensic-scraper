# Create GitHub repo and push (uses same token as Cursor GitHub MCP)
# Requires: token in %USERPROFILE%\.github-mcp-token (one line) OR $env:GITHUB_TOKEN
# Or: install GitHub CLI (winget install GitHub.cli) and run: gh auth login

$ErrorActionPreference = "Stop"
$repoName = "death-star-forensic-scraper"
$description = "Full forensic web scraper - WARC, HAR, DOM, assets. One command, any target."

# 1) Try gh CLI
$gh = Get-Command gh -ErrorAction SilentlyContinue
if ($gh) {
    Write-Host "Using GitHub CLI..."
    & gh auth status 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Run: gh auth login"
        exit 1
    }
    & gh repo create $repoName --public --description $description --source . --remote origin --push
    if ($LASTEXITCODE -eq 0) { Write-Host "Done."; exit 0 }
    # May fail if repo already exists; then just add remote and push
}

# 2) Token from file (same as .cursor\scripts\github-mcp.cmd) or env
$tokenFile = Join-Path $env:USERPROFILE ".github-mcp-token"
$token = $env:GITHUB_TOKEN
if (-not $token -and (Test-Path $tokenFile)) {
    $token = (Get-Content $tokenFile -Raw).Trim()
}
if (-not $token) {
    Write-Host "No GitHub CLI and no token found."
    Write-Host "  Option A: Create $tokenFile with your GitHub token (one line, no quotes)."
    Write-Host "  Option B: winget install GitHub.cli then run: gh auth login"
    exit 1
}

# 3) Create repo via API and push
$headers = @{
    "Authorization" = "token $token"
    "Accept"        = "application/vnd.github.v3+json"
}
$body = @{
    name        = $repoName
    description = $description
    private     = $false
    auto_init   = $false
} | ConvertTo-Json

$user = Invoke-RestMethod -Uri "https://api.github.com/user" -Headers @{ "Authorization" = "token $token"; "Accept" = "application/vnd.github.v3+json" }
$login = $user.login

$create = Invoke-RestMethod -Uri "https://api.github.com/user/repos" -Method Post -Headers $headers -Body $body -ContentType "application/json"
$cloneUrl = $create.clone_url
# HTTPS push: username is login, password is token
$pushUrl = "https://${login}:${token}@github.com/${login}/${repoName}.git"

if (git remote get-url origin 2>$null) {
    git remote remove origin
}
git remote add origin $pushUrl
git branch -M main
git push -u origin main
Write-Host "Pushed to https://github.com/$login/$repoName"
# Remove token from remote for future pulls (use credential helper)
git remote set-url origin $cloneUrl
