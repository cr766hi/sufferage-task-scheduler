param([switch]$Preview)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Python .venv belum tersedia pada proyek.' }
if (-not $Preview) {
    $clients = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -match '(^|[\\/\s"])run_scheduler\.py(["\s]|$)'
    })
    if ($clients.Count -gt 0) {
        throw 'Script run_scheduler.py masih berjalan. Tunggu pengujian/pengambilan hasil selesai sebelum membersihkan CSV.'
    }
}
$cleanupArgs = @((Join-Path $PSScriptRoot 'clean_results.py'))
if ($Preview) { $cleanupArgs += '--preview' }
& $pythonPath @cleanupArgs
if ($LASTEXITCODE -ne 0) { throw 'Pembersihan belum selesai. Periksa pesan di atas.' }
