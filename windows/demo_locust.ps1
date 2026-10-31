param(
    [ValidateSet('stable', 'spike', 'fault')]
    [string]$Scenario = 'stable',
    [ValidateRange(15, 600)]
    [int]$Duration = 60
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Virtual environment belum ditemukan: $pythonPath. Jalankan python -m venv .venv dari akar repo, lalu install windows/requirements.txt."
}
$healthText = & curl.exe --noproxy '*' --fail --silent --show-error --max-time 10 'http://192.168.56.10/__lb/health'
if ($LASTEXITCODE -ne 0) { throw 'LB belum siap. Jalankan LB di vm210 terlebih dahulu.' }
$health = ($healthText -join "`n") | ConvertFrom-Json
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$demoDirectory = Join-Path $projectRoot "results\demo\$stamp-$Scenario-$($health.algorithm)"
New-Item -ItemType Directory -Path $demoDirectory -Force | Out-Null
$environmentNames = @('SCENARIO', 'DURATION', 'REQUEST_CSV', 'RUN_SEED')
$previousEnvironment = @{}
foreach ($name in $environmentNames) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
try {
    $env:SCENARIO = $Scenario
    $env:DURATION = [string]$Duration
    $env:REQUEST_CSV = Join-Path $demoDirectory 'client.csv'
    $env:RUN_SEED = '1001'
    Write-Host "Algoritma LB saat ini: $($health.algorithm)"
    Write-Host "Skenario: $Scenario, durasi: $Duration detik"
    Write-Host "Backend sehat: $(($health.backends | Where-Object healthy).Count)/4"
    Write-Host 'Buka http://127.0.0.1:8089 lalu mulai tes SATU KALI dari antarmuka Locust.'
    Write-Host 'Jumlah user mengikuti ScenarioShape, bukan diatur manual dari UI.'
    Write-Host 'Setelah tes selesai, Ctrl+C, lalu jalankan skrip ini lagi untuk tes berikutnya.'
    Write-Host "Output demo: $demoDirectory"
    if ($Scenario -eq 'fault') {
        Write-Host 'FAULT: skrip ini hanya menghasilkan trafik. Pemadaman VM dilakukan manual atau oleh run_experiments.py.'
    }
    & $pythonPath -m locust -f (Join-Path $PSScriptRoot 'locustfile.py') `
        --host 'http://192.168.56.10' --web-host '127.0.0.1' --web-port 8089 `
        --stop-timeout 8 --csv (Join-Path $demoDirectory 'locust')
} finally {
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process')
    }
}
