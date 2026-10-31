<# GameForge verification gate (P0 WI-0.12).
   -Quick : unit + protected suites + op-catalogue and op-schema drift (no engine).
   Full   : also the live editor contract on a disposable probe copy, one engine demo and the IDE benchmark. #>
param([switch]$Quick)
$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
New-Item -ItemType Directory -Force "$repo\scratch\pytest_os_temp" | Out-Null
$env:TEMP = "$repo\scratch\pytest_os_temp"; $env:TMP = $env:TEMP
if (-not $env:GAMEFORGE_HOST_PROFILE) { $env:GAMEFORGE_HOST_PROFILE = "$repo\configs\host_profiles\dev-rx7700xt.json" }
$results = [ordered]@{}
function Gate([string]$name, [scriptblock]$cmd) {
    Write-Host "== $name" -ForegroundColor Cyan
    & $cmd
    $script:results[$name] = if ($LASTEXITCODE -eq 0) { "PASS" } else { "FAIL ($LASTEXITCODE)" }
}
Gate "unit"        { python -m pytest tests/unit/ -q -p no:cacheprovider }
Gate "protected"   { python -m pytest graders/protected/ -q -p no:cacheprovider }
Gate "op-catalog"  { python scripts/tools/gen_op_coverage.py --check }
Gate "op-schemas"  { python scripts/tools/gen_op_schemas.py --check }
if (-not $Quick) {
    Gate "contract"   { python scripts/engine/live_editor_contract_test.py --disposable }
    Gate "demo-quest" { python scripts/engine/demo_m15_quest.py }
    Gate "ide-bench"  { python scripts/ide/ide_resource_benchmark.py --workspace E:\GameForge\ide_bench_ws }
}
Write-Host ""
$results.GetEnumerator() | ForEach-Object { "{0,-12} {1}" -f $_.Key, $_.Value }
if ($results.Values | Where-Object { $_ -ne "PASS" }) { exit 1 } else { exit 0 }
