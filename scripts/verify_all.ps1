<# GameForge verification gate (P0 WI-0.12).
   -Quick          : unit + protected suites + op-catalogue and op-schema drift (no engine).
   -UnitOnly       : run only the unit test suite.
   -ProtectedOnly  : run only the protected graders suite.
   Full            : also the live editor contract on a disposable probe copy, one engine demo and the IDE benchmark. #>
param(
    [switch]$Quick,
    [switch]$UnitOnly,
    [switch]$ProtectedOnly
)
$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
New-Item -ItemType Directory -Force "$repo\scratch\pytest_os_temp" | Out-Null
$env:TEMP = "$repo\scratch\pytest_os_temp"; $env:TMP = $env:TEMP

if (-not $env:GAMEFORGE_HOST_PROFILE) {
    $devProf = "$repo\configs\host_profiles\dev-rx7700xt.json"
    if (Test-Path $devProf) {
        $env:GAMEFORGE_HOST_PROFILE = $devProf
    } else {
        $foundProf = Get-ChildItem "$repo\configs\host_profiles\*.json" | Select-Object -First 1
        if ($foundProf) {
            $env:GAMEFORGE_HOST_PROFILE = $foundProf.FullName
        }
    }
}

$results = [ordered]@{}
function Gate([string]$name, [scriptblock]$cmd) {
    Write-Host "== $name" -ForegroundColor Cyan
    $LASTEXITCODE = 0
    try {
        & $cmd
        $ec = $LASTEXITCODE
        if ($ec -eq 0 -and $?) {
            $script:results[$name] = "PASS"
        } else {
            $script:results[$name] = "FAIL ($ec)"
        }
    } catch {
        $script:results[$name] = "FAIL (exception: $($_.Exception.Message))"
    }
}

if ($UnitOnly) {
    Gate "unit" { python -m pytest tests/unit/ -q -p no:cacheprovider }
} elseif ($ProtectedOnly) {
    Gate "protected" { python -m pytest graders/protected/ -q -p no:cacheprovider }
} else {
    Gate "unit"        { python -m pytest tests/unit/ -q -p no:cacheprovider }
    Gate "protected"   { python -m pytest graders/protected/ -q -p no:cacheprovider }
    Gate "op-catalog"  { python scripts/tools/gen_op_coverage.py --check }
    Gate "op-schemas"  { python scripts/tools/gen_op_schemas.py --check }
    if (-not $Quick) {
        Gate "contract"   { python scripts/engine/live_editor_contract_test.py --disposable }
        Gate "demo-quest" { python scripts/engine/demo_m15_quest.py }
        $benchWs = if (Test-Path "E:\GameForge\ide_bench_ws") { "E:\GameForge\ide_bench_ws" } else { "$repo\scratch\bench_ws" }
        New-Item -ItemType Directory -Force $benchWs | Out-Null
        Gate "ide-bench"  { python scripts/ide/ide_resource_benchmark.py --workspace $benchWs }
    }
}

Write-Host ""
$results.GetEnumerator() | ForEach-Object { "{0,-12} {1}" -f $_.Key, $_.Value }
if ($results.Values | Where-Object { $_ -ne "PASS" }) { exit 1 } else { exit 0 }
