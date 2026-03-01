param (
    [Parameter(Mandatory=$true, Position=0)]
    [string]$NewToken
)

if ([string]::IsNullOrWhiteSpace($NewToken)) {
    Write-Host "Usage: .\at.ps1 <access_token>" -ForegroundColor Yellow
    exit 1
}

$envPath = Join-Path -Path $PSScriptRoot -ChildPath ".env"
$content = if (Test-Path $envPath) { Get-Content $envPath } else { @() }
$foundAccess = $false
$foundUpstox = $false

$newContent = @()
foreach ($line in $content) {
    if ($line -match '^ACCESS_TOKEN=') {
        $foundAccess = $true
        $newContent += "ACCESS_TOKEN=$NewToken"
    } elseif ($line -match '^UPSTOX_ACCESS_TOKEN=') {
        $foundUpstox = $true
        $newContent += "UPSTOX_ACCESS_TOKEN=$NewToken"
    } else {
        $newContent += $line
    }
}

if (-not $foundAccess) { $newContent += "ACCESS_TOKEN=$NewToken" }
if (-not $foundUpstox) { $newContent += "UPSTOX_ACCESS_TOKEN=$NewToken" }

$newContent | Set-Content -Path $envPath -Encoding UTF8
Write-Host "✅ Local .env updated with token." -ForegroundColor Green

$repo = "71762132036-wq/web_service"
Write-Host "Pushing to GitHub Secrets..." -ForegroundColor Cyan

# Check if gh CLI is installed
if (Get-Command "gh" -ErrorAction SilentlyContinue) {
    try {
        $ghOutput = gh secret set UPSTOX_ACCESS_TOKEN --body $NewToken --repo $repo 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ GitHub secret UPSTOX_ACCESS_TOKEN updated for repo $repo." -ForegroundColor Green
            Write-Host "Success: ACCESS_TOKEN has been updated locally and in GitHub." -ForegroundColor Green
        } else {
            Write-Host "❌ Failed to set GitHub secret. Are you authenticated with 'gh auth login'?" -ForegroundColor Red
            Write-Host $ghOutput -ForegroundColor Red
        }
    } catch {
        Write-Host "❌ Failed to execute gh command. Error: $_" -ForegroundColor Red
    }
} else {
    Write-Host "⚠️ GitHub CLI ('gh') is not installed. Skipping GitHub Secret update." -ForegroundColor Yellow
    Write-Host "👉 To update GitHub automatically, install it via: winget install --id GitHub.cli" -ForegroundColor Yellow
    Write-Host "Success: ACCESS_TOKEN has been updated locally." -ForegroundColor Green
}

# Make command usable from anywhere by adding folder to User PATH
$scriptDir = $PSScriptRoot
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notmatch [regex]::Escape($scriptDir)) {
    Write-Host "Adding $scriptDir to your User PATH so 'at' works from anywhere..." -ForegroundColor Cyan
    $newPath = $userPath + ";" + $scriptDir
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "✅ Added! You may need to open a NEW terminal window for the global 'at' command to work." -ForegroundColor Green
}

