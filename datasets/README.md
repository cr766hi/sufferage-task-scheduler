# Dataset input task scheduling

Setiap CSV adalah satu batch task independen. Seluruh task datang bersamaan.
Task ID unik di dalam batch; urutan tetap diacak dengan seed 42 agar dapat diulang.
Tidak ada durasi tidur buatan. Worker benar-benar menghitung PBKDF2-SHA256.

| Dataset | Total | Ringan/light | Sedang/medium | Berat/heavy | Penggunaan |
|---|---:|---:|---:|---:|---|
| `demo40.csv` | 40 | 20 | 12 | 8 | Referensi uji verifikasi terdahulu |
| `demo120.csv` | 120 | 60 | 36 | 24 | Default demo |
| `demo240.csv` | 240 | 120 | 72 | 48 | Batch lebih besar |
| `demo500.csv` | 500 | 250 | 150 | 100 | Batas maksimum satu batch |

| Jenis task | Unit CPU | Iterasi per unit | Total iterasi | Rasio kerja |
|---|---:|---:|---:|---:|
| light / ringan | 2 | 1.000 | 2.000 | 1 |
| medium / sedang | 8 | 1.000 | 8.000 | 4 |
| heavy / berat | 24 | 1.000 | 24.000 | 12 |

Kolom: `task_id`, `task_type`, `units`, `iterations_per_unit`. Task bercampur dalam
urutan dataset, bukan dikelompokkan per jenis. Ini memungkinkan scheduler memilih
task dari seluruh kandidat berdasarkan Sufferage, bukan mengikuti urutan jenis.
Ukuran kerja sama pada setiap worker; VM dua vCPU membagi unit ke dua proses.
Rasio kerja tidak menjamin rasio waktu aktual karena overhead dan kontensi.

## Jalankan dari akar proyek

```powershell
.\windows\demo_scheduler.ps1
.\windows\demo_scheduler.ps1 -Dataset datasets\demo240.csv -ReuseCalibration
.\windows\demo_scheduler.ps1 -Dataset datasets\demo500.csv -ReuseCalibration
```

Jalankan satu per satu setelah batch sebelumnya selesai. Default mengkalibrasi
ETC sebelum submit. `-ReuseCalibration` memakai ETC yang sama bila sudah tersedia.
Untuk membuat dataset khusus tanpa menimpa file yang sudah ada:

```powershell
.\.venv\Scripts\python.exe windows\generate_dataset.py --tasks 200 --seed 42 --output datasets\demo200.csv
```

Generator menerima 1–500 task dan tidak menimpa file existing. Proporsi target
50/30/20; jumlah yang tidak habis dibagi dibulatkan untuk ringan/sedang dan sisanya
menjadi berat. Dataset yang lebih besar belum mempunyai klaim hasil performa baru;
laporan tiga pengulangan sebelumnya tetap memakai 40 task.
