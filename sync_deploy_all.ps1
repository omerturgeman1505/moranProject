$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Report = Join-Path $Root "agent_run_report.txt"
$Sa = "C:\Users\omert\Downloads\moran-cce72-firebase-adminsdk-fbsvc-55d361cb9b.json"
$NodeDir = "C:\Users\omert\AppData\Local\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.16.0-win-x64"

function Log($msg) { Add-Content -Path $Report -Value $msg; Write-Host $msg }

"" | Set-Content $Report
Log "=== Moran sync/deploy run $(Get-Date -Format o) ==="

# Sync github_upload
$Up = Join-Path $Root "github_upload"
Copy-Item -Force (Join-Path $Root "public\index.html") (Join-Path $Up "public\index.html")
Copy-Item -Force (Join-Path $Root "public\job_sections.js") (Join-Path $Up "public\job_sections.js")
Copy-Item -Force (Join-Path $Root "job_sections.py") (Join-Path $Up "job_sections.py")
Copy-Item -Force (Join-Path $Root "job_search_platform.py") (Join-Path $Up "job_search_platform.py")
Copy-Item -Force (Join-Path $Root "daily_scan.py") (Join-Path $Up "daily_scan.py")
Copy-Item -Force (Join-Path $Root "moran_profile.py") (Join-Path $Up "moran_profile.py")
Copy-Item -Force (Join-Path $Root "test_job_sections.py") (Join-Path $Up "test_job_sections.py")
Copy-Item -Force (Join-Path $Root "PROJECT.md") (Join-Path $Up "PROJECT.md")
Log "Sync github_upload: OK"

Log "--- unittest ---"
python -m unittest test_job_sections.py test_job_search_platform.py -v 2>&1 | ForEach-Object { Log $_ }

Log "--- py_compile ---"
python -m py_compile job_search_platform.py daily_scan.py moran_profile.py job_sections.py web_app.py 2>&1 | ForEach-Object { Log $_ }
Log "py_compile: OK"

Log "--- daily_scan ---"
$env:FIREBASE_SERVICE_ACCOUNT = $Sa
python daily_scan.py 2>&1 | ForEach-Object { Log $_ }

Log "--- firebase deploy ---"
$env:GOOGLE_APPLICATION_CREDENTIALS = $Sa
$env:PATH = "$NodeDir;$env:PATH"
firebase deploy --only hosting,database --project moran-cce72 2>&1 | ForEach-Object { Log $_ }

Log "--- git root ---"
if (Test-Path (Join-Path $Root ".git")) {
  Set-Location $Root
  Log "Git repo: root"
} elseif (Test-Path (Join-Path $Up ".git")) {
  Set-Location $Up
  Log "Git repo: github_upload"
} else {
  Log "No git repo found"
  exit 0
}

git status --short 2>&1 | ForEach-Object { Log $_ }
git add -A 2>&1 | ForEach-Object { Log $_ }
git reset HEAD -- .env service-account.json 2>$null
git reset HEAD -- "*.sqlite3" "*.sqlite" "*.db" 2>$null
git commit -m "Sync job summary sections across hosting, backend, and github_upload" 2>&1 | ForEach-Object { Log $_ }
git push origin HEAD 2>&1 | ForEach-Object { Log $_ }

Log "--- gh workflow ---"
gh workflow run manual-scan.yml --repo omerturgeman1505/moranProject 2>&1 | ForEach-Object { Log $_ }

Log "=== DONE ==="
