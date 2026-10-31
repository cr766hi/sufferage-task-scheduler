param(
    [string]$Dataset = 'datasets\demo120.csv',
    [switch]$ReuseCalibration,
    [string]$Resume
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Buat .venv terlebih dahulu: python -m venv .venv' }
$schedulerArgs = @((Join-Path $PSScriptRoot 'run_scheduler.py'))
if ($Resume) {
    $schedulerArgs += @('--resume', $Resume)
} else {
    if (-not [IO.Path]::IsPathRooted($Dataset)) { $Dataset = Join-Path $projectRoot $Dataset }
    $schedulerArgs += @('--dataset', $Dataset)
    if ($ReuseCalibration) { $schedulerArgs += '--reuse-calibration' }
}
Write-Host 'Task scheduler Sufferage: dataset batch -> vm210 -> empat VM worker'
& $pythonPath @schedulerArgs
if ($LASTEXITCODE -ne 0) { throw 'Pengujian gagal. Lihat pesan di atas; batch yang sudah dikirim bisa diambil dengan -Resume latest.' }
