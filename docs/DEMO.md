# Demo task scheduling Sufferage

## 1. Nyalakan infrastruktur

Nyalakan pve1/pve2 pada VirtualBox, lalu pastikan VM 101/102/201/202/210 running.
Tunggu boot 1–2 menit dan periksa guest benar-benar siap. Worker dan scheduler
memiliki autostart OpenRC. Hostname vm210 tetap `vm-lb` sebagai identitas lama;
program aktifnya sekarang task scheduler.

## 2. Buka dataset dan cek scheduler di PowerShell

```powershell
cd E:\testsokarealworld
Get-Content .\datasets\demo120.csv | Select-Object -First 8
curl.exe --noproxy '*' http://192.168.56.10/api/health
```

Tunjukkan Task ID, jenis pekerjaan dan unit CPU. Health harus menunjukkan
`role: task_scheduler`, `algorithm: sufferage`, `scheduling: offline_batch`,
dan empat worker sehat. `calibrated: false` sebelum run pertama adalah normal.

## 3. PowerShell kedua: SSH ke vm210

```powershell
ssh root@192.168.56.10
```

Masukkan password lewat prompt; setelah masuk:

```sh
hostname
rc-service task-scheduler status
grep -n 'def sufferage_plan' /opt/sufferage-scheduler/sufferage.py
tail -f /var/log/sufferage-scheduler/service.log
```

Biarkan log terbuka. Nanti terlihat event `calibrated`, `task_started`,
`task_terminal`, dan `batch_finished` beserta Task ID dan worker. Ini log proses
nyata di VM, bukan log simulasi Windows.

## 4. PowerShell pertama: kirim batch dataset

```powershell
.\windows\demo_scheduler.ps1
```

Script mengukur ETC v2 dengan tujuh sampel RPC per jenis task pada tiap VM
(di luar makespan), lalu mengirim
120 task sekaligus. vm210 menghitung seluruh jadwal Sufferage sebelum eksekusi.
Task logis dijalankan satu per satu pada setiap worker, empat antrean berjalan
paralel. Tunjukkan progress `N/120 task`, dan pindah ke SSH untuk melihat log live.
Tidak ada Start Locust atau jumlah user virtual pada eksperimen ini.

## 5. Setelah batch selesai, buka tabel

Buka `E:\testsokarealworld\hasil_pengujian.html`, lalu Refresh. Urutan penjelasan:

1. Task selesai, makespan, rata-rata waiting/turnaround, throughput task.
2. Alokasi ringan/sedang/berat dan jumlah task tiap VM.
3. CPU/RAM worker dan scheduler.
4. Buka **Jejak Sufferage**: CT empat kandidat, selisih terbaik/kedua dan worker pilihan.
5. Buka **Waktu eksekusi task**: start, finish, waiting, execution, turnaround.
6. Buka matriks ETC untuk menunjukkan input estimasi penjadwalan.

Semua detail berada dalam satu `results/pengujian N.csv` per batch.
CSV pengujian HTTP lama diabaikan oleh halaman scheduling.

## 6. Tunjukkan file hasil di dalam VM

Pada SSH, Ctrl+C untuk menghentikan tampilan `tail`, bukan scheduler:

```sh
latest=$(ls -td /var/log/sufferage-scheduler/batch-* | head -n 1)
head -n 6 "$latest/tasks.csv"
wget -qO- http://127.0.0.1/api/batches/latest?summary=1 | python3 -m json.tool
```

Hasil batch bertahan pada `result.json` di direktori yang sama. Untuk pengulangan
dengan dataset dan ETC yang sama, jalankan dari Windows:

```powershell
.\windows\demo_scheduler.ps1 -ReuseCalibration
```

Jika client terputus setelah submit, jangan mengirim ulang tanpa memeriksa status:

```powershell
.\windows\demo_scheduler.ps1 -Resume latest
```

Percobaan fault bukan bagian demo utama revisi ini. Worker gagal dicatat, task
tersisa pada antrean worker tersebut di-skip; tidak ada retry atau migrasi task otomatis.

## Pilihan jumlah task

Default sekarang 120 task: 60 ringan, 36 sedang, 24 berat. Sebelum kalibrasi,
script mencetak jumlah ketiga jenis task sehingga komposisi input terlihat.

Untuk 240 task:

```powershell
.\windows\demo_scheduler.ps1 -Dataset datasets\demo240.csv -ReuseCalibration
```

Untuk 500 task:

```powershell
.\windows\demo_scheduler.ps1 -Dataset datasets\demo500.csv -ReuseCalibration
```

Gunakan tanpa `-ReuseCalibration` jika ingin mengukur ulang ETC. Jumlah task besar
menambah waktu planning dan eksekusi pada laptop emulasi. Batas scheduler 500 task
per batch. Bandingkan pengulangan dengan dataset dan ETC yang sama; jumlah task
berbeda tidak menunjukkan perbedaan algoritma. Rincian ada pada [dataset](../datasets/README.md).

## Menjelaskan kualitas penjadwalan saat demo

Tunjukkan timeline task dan tabel kualitas ETC. MAPE mengukur selisih absolut
ETC terhadap durasi RPC aktual dibagi durasi aktual; lebih rendah berarti prediksi
lebih dekat pada pengukuran run tersebut. Lihat waktu selesai dan jeda akhir
worker, bukan mengharuskan persentase CPU semua VM sama. CPU dinormalisasi
terhadap seluruh vCPU VM. Task sedikit bisa memiliki lebih banyak unit kerja.

Kalibrasi v2 lebih lama daripada dua sampel sebelumnya, tetapi dilakukan sebelum
batch. Untuk mengulang dataset yang sama, gunakan `-ReuseCalibration`. Jangan
membandingkan v1/v2 sebagai benchmark terkontrol tanpa pengulangan dengan kondisi
yang sama. Sampling singkat dan kontensi emulasi tetap perlu dijelaskan.
