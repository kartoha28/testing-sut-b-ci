param(
    [ValidateSet("baseline", "load", "stress")]
    [string]$Profile = "baseline"
)

$k6Path = "$PSScriptRoot\..\tools\k6.exe"
$scenarioPath = "$PSScriptRoot\k6\scenario.js"
$reportPath = "$PSScriptRoot\k6\reports\${Profile}_report.html"
$jsonPath = "$PSScriptRoot\k6\reports\${Profile}_summary.json"

New-Item -ItemType Directory -Force "$PSScriptRoot\k6\reports" | Out-Null

Write-Host ">>> Running k6 test profile: $Profile" -ForegroundColor Cyan

$env:K6_WEB_DASHBOARD = "true"
$env:K6_WEB_DASHBOARD_EXPORT = $reportPath
$env:K6_WEB_DASHBOARD_PORT = "-1"

& $k6Path run -e "PROFILE=$Profile" --summary-export $jsonPath $scenarioPath

Write-Host ">>> HTML report generated at: $reportPath" -ForegroundColor Green
