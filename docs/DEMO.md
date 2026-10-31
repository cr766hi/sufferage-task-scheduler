# Demo Sufferage: nyalakan, cek, jalankan Locust, lihat hasil

## 1. Nyalakan infrastruktur

Nyalakan pve1/pve2 di VirtualBox. Tunggu Proxmox siap, lalu pastikan VM
101, 102, 201, 202, dan 210 berstatus running. Tunggu guest selesai boot.
Layanan `sufferage-lb` otomatis mulai saat vm210 boot.

## 2. Cek LB dari PowerShell

```powershell
curl.exe --noproxy '*' http://192.168.56.10/__lb/health
```

Hasil harus menunjukkan `"algorithm": "sufferage"` dan keempat backend
`"healthy": true`. `queued` menunjukkan antrean masuk; `active` menunjukkan
request upstream aktif yang dihitung LB. Nilai ini bukan persentase CPU.

Jika perlu, cek backend satu per satu:

```powershell
curl.exe --noproxy '*' http://192.168.56.21/
curl.exe --noproxy '*' http://192.168.56.22/
curl.exe --noproxy '*' http://192.168.56.31/
curl.exe --noproxy '*' http://192.168.56.32/
```

Responsnya berturut-turut harus `vm101`, `vm102`, `vm201`, dan `vm202`.
VM running pada Proxmox belum menjamin Alpine berhasil boot. vm101 pernah
kernel panic IO-APIC; cek konsol bila belum siap setelah waktu boot yang wajar.

## 3. Tunjukkan output keputusan Sufferage

```powershell
curl.exe --noproxy '*' -i http://192.168.56.10/
```

Contoh format respons; backend yang muncul dapat berbeda:

```text
HTTP/1.1 200 OK
X-LB-Backend: vm102
X-LB-Algorithm: sufferage

vm102
```

Artinya request diterima vm210, dipilihkan backend vm102, dan nginx vm102
menghasilkan body tersebut. Untuk beberapa request:

```powershell
1..8 | ForEach-Object { curl.exe --noproxy '*' -sS -i http://192.168.56.10/ }
```

## 4. Siapkan Python Windows sekali saja

Clone repo private memakai akun yang punya akses, lalu buka PowerShell pada akar repo:

```powershell
git clone https://github.com/cr766hi/sufferage-load-balancer.git
Set-Location sufferage-load-balancer
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r windows\requirements.txt
```

Tidak perlu mengaktifkan virtual environment; gunakan path Python-nya langsung.
Jika sudah dibuat, cukup masuk ke folder repo pada demo berikutnya.

## 5. Jalankan Locust dan buka grafik

```powershell
.\windows\demo_locust.ps1 -Scenario stable -Duration 60
```

Buka **http://127.0.0.1:8089**, lalu klik mulai tes satu kali. Helper membaca mode
LB yang aktif; tidak memasang LB atau mengganti algoritma di vm210.

Tunjukkan statistik request, failures, response time, dan request/s. Pada tab
grafik, tunjukkan response time, throughput dan jumlah user terhadap waktu.
Jumlah user mengikuti `ScenarioShape` dalam `locustfile.py`, bukan diisi bebas:

| Skenario | Pola 60 detik |
|---|---|
| `stable` | 10 user sepanjang tes |
| `spike` | 10 user pada 0–20 s, 40 pada 20–40 s, 10 pada 40–60 s |
| `fault` | 10 user; pemadaman VM tidak dilakukan oleh helper ini |

Setelah tes selesai, Ctrl+C di terminal Locust, lalu jalankan helper lagi untuk
tes berikutnya. Setiap proses helper membuat folder hasil baru. Jangan klik
Start berkali-kali dalam proses yang sama karena file CSV per-request harus baru.

Contoh spike:

```powershell
.\windows\demo_locust.ps1 -Scenario spike -Duration 60
```

Jika `.ps1` ditolak kebijakan PowerShell, gunakan Python langsung tanpa mengubah
kebijakan keamanan Windows:

```powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$folder = Join-Path (Get-Location) "results\demo\$stamp"
New-Item -ItemType Directory -Path $folder -Force | Out-Null
$env:SCENARIO = 'stable'
$env:DURATION = '60'
$env:REQUEST_CSV = Join-Path $folder 'client.csv'
$env:RUN_SEED = '1001'
.\.venv\Scripts\python.exe -m locust -f windows\locustfile.py --host http://192.168.56.10 --web-host 127.0.0.1 --web-port 8089 --stop-timeout 8 --csv (Join-Path $folder 'locust')
```

## 6. Lihat file hasil di Windows

```text
results/demo/<waktu>-stable-sufferage/
├── client.csv             # setiap request dari Windows
├── client.json            # durasi ukur dan konfigurasi
├── client.started.json    # waktu mulai
├── locust_stats.csv       # snapshot statistik berkala
├── locust_stats_history.csv
└── locust_failures.csv
```

Contoh kolom `client.csv`:

```csv
timestamp,scenario,request_id,backend,response_time_ms,status,error
```

Itu merupakan hasil dari sisi klien. CSV statistik bawaan Locust bersifat
periodik; log per-request dapat mencakup request terakhir yang belum ada dalam
snapshot statistik. Benchmark sebelumnya menggunakan log per-request yang
dicocokkan dengan LB.

## 7. Lihat CSV Sufferage di vm210

SSH dari terminal PowerShell lain:

```powershell
ssh root@192.168.56.10
```

Di shell vm210:

```sh
rc-service sufferage-lb status
ls -td /var/log/sufferage-lb/run-*
latest=$(ls -td /var/log/sufferage-lb/run-* | head -n 1)
tail -n 10 "$latest/requests.csv"
```

Untuk menonton log request yang terus bertambah:

```sh
tail -f "$latest/requests.csv"
```

Ctrl+C menghentikan tampilan `tail`, bukan layanan. CSV di-flush berkala,
sehingga baris baru bisa muncul dalam kelompok.

Kolom penting:

| Kolom | Artinya |
|---|---|
| `algoritma` | Mode yang melayani request: sufferage |
| `backend` | VM tujuan pilihan LB |
| `response_time_ms` | Waktu dari sisi LB sampai respons disiapkan |
| `queue_ms` | Waktu sebelum dispatch, termasuk batching dan antrean event loop |
| `upstream_ms` | Waktu transaksi HTTP ke backend |
| `estimated_work_ms` | Estimasi kerja pada kapasitas satu saat request masuk |
| `status` | Status HTTP; 200 sukses, 502 kegagalan upstream |
| `request_id` | Penghubung baris LB dengan baris di CSV Locust |

Contoh request nyata tersedia pada [examples/lb-request.csv](../examples/lb-request.csv)
dan [examples/client-request.csv](../examples/client-request.csv). Waktu respons
klien berbeda dari waktu LB karena mencakup perjalanan end-to-end dari Windows.

## 8. Fault dan batas output saat ini

Untuk demo singkat, cukup stabil/spike dan jelaskan hasil fault yang sudah
direkam. Jika melakukan fault live, matikan hanya satu **VM backend**, misalnya
VM 101, lalu pulihkan setelah tes. Jangan mematikan pve1, pve2, atau vm210.
Siapkan waktu boot tambahan dan periksa kesiapan guest kembali.

Health check membuang backend gagal dari kandidat. Request yang terlanjur dikirim
masih dapat gagal 502. `windows/locustfile.py` hanya menghasilkan trafik;
benchmark otomatis menggunakan [runner](../experiments/run_experiments.py).

CSV saat ini menunjukkan keputusan backend dan estimasi kerja. CSV belum
mencatat seluruh matriks CT dan nilai Sufferage setiap kandidat. Untuk menjelaskan
langkah matematisnya, tampilkan `sufferage_plan()` dan contoh pada
[cara kerja algoritma](SUFFERAGE.md). Tidak ada dashboard khusus scheduler yang
diklaim terpasang; grafik yang ditampilkan adalah grafik pengukuran Locust.
