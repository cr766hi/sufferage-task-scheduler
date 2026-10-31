# Demo task scheduling Sufferage

## 1. Nyalakan infrastruktur

Nyalakan pve1/pve2 pada VirtualBox, lalu pastikan VM 101/102/201/202/210 running.
Tunggu boot 1–2 menit dan periksa guest benar-benar siap. Worker dan scheduler
memiliki autostart OpenRC. Hostname vm210 tetap `vm-lb` sebagai identitas lama;
program aktifnya sekarang task scheduler.

## 2. Buka dataset dan cek scheduler di PowerShell

```powershell
cd E:\testsokarealworld
Get-Content .\datasets\demo40.csv | Select-Object -First 8
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

Script mengukur ETC tiap jenis task pada tiap VM (di luar makespan), lalu mengirim
40 task sekaligus. vm210 menghitung seluruh jadwal Sufferage sebelum eksekusi.
Task logis dijalankan satu per satu pada setiap worker, empat antrean berjalan
paralel. Tunjukkan progress `N/40 task`, dan pindah ke SSH untuk melihat log live.
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

## Opsional: batch lebih panjang untuk demonstrasi log dan sampling CPU

```powershell
.\windows\demo_scheduler.ps1 -Dataset datasets\demo120.csv -ReuseCalibration
```

Dataset ini berisi 120 task (60 light, 36 medium, 24 heavy). Jumlah kerja meningkat;
tidak ada penundaan buatan. Jangan membandingkan makespan dataset 40 dan 120 task
sebagai perbedaan algoritma. Untuk pengulangan, pilih dataset yang sama.
