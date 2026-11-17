param(
    [ValidateSet("baseline", "load", "stress")]
    [string]$Profile = "baseline"
)

$toolsDir = "$PSScriptRoot\..\tools"
$env:JAVA_HOME = "$toolsDir\jre"
$env:PATH = "$toolsDir\jre\bin;$env:PATH"

$jmeterBat = "$toolsDir\jmeter\bin\jmeter.bat"
$scenarioJmx = "$PSScriptRoot\jmeter\scenario.jmx"
$reportsDir = "$PSScriptRoot\jmeter\reports"
$jtlPath = "$reportsDir\${Profile}.jtl"
$htmlReportDir = "$reportsDir\${Profile}_report"

New-Item -ItemType Directory -Force $reportsDir | Out-Null
Remove-Item $jtlPath -ErrorAction SilentlyContinue
Remove-Item $htmlReportDir -Recurse -Force -ErrorAction SilentlyContinue

switch ($Profile) {
    "baseline" {
        $threads = 1
        $rampup = 2
        $duration = 20
    }
    "load" {
        $threads = 10
        $rampup = 10
        $duration = 50
    }
    "stress" {
        $threads = 30
        $rampup = 10
        $duration = 40
    }
}

Write-Host ">>> Running JMeter test profile: $Profile (Threads: $threads, RampUp: $rampup s, Duration: $duration s)" -ForegroundColor Cyan

$jmeterArgs = @(
    "-n",
    "-t", $scenarioJmx,
    "-l", $jtlPath,
    "-e",
    "-o", $htmlReportDir,
    "-Jthreads=$threads",
    "-Jrampup=$rampup",
    "-Jduration=$duration",
    "-Jjmeter.reportgenerator.overall_granularity=2000"
)

& $jmeterBat $jmeterArgs

Write-Host ">>> JMeter HTML report generated at: $htmlReportDir\index.html" -ForegroundColor Green
