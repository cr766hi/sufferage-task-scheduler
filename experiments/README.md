# Kode benchmark pembanding sebelumnya

Untuk demo operasional, gunakan layanan Sufferage dan script Windows. Folder ini
menyimpan otomasi yang digunakan saat membandingkan tiga algoritma. Penyesuaian
path sudah dilakukan agar source LB dibaca dari `vm210/lb.py`, Locust dari
`windows/locustfile.py`, dan hasil ditulis ke `results/` pada akar repo.

- `run_experiments.py`: deployment proses LB, 27 run, fault, pemulihan, resume.
- `summarize.py`: mean, p95, throughput, error rate, raw/normalized imbalance.
- `verify_results.py`: pasangan ID klien/LB, jumlah request, dan waktu fault.

Runner memakai SSH host Proxmox untuk `qm stop 101` dan `qm start 101` pada tes
fault. Tidak pernah mematikan pve1/pve2. Password diminta dari prompt, tidak disimpan.

Jangan jalankan runner bersamaan dengan layanan OpenRC atau demo Locust lain.
Hentikan layanan `sufferage-lb` dahulu jika sengaja mengulang benchmark.
Runner meninggalkan proses nohup Sufferage pada akhir sesi; hentikan instance
nohup milik sesi itu sebelum mengaktifkan kembali layanan OpenRC, agar tidak
terjadi konflik port 80.

```powershell
.\.venv\Scripts\python.exe experiments\run_experiments.py --duration 60 --repeats 3
.\.venv\Scripts\python.exe experiments\verify_results.py results\<session>
.\.venv\Scripts\python.exe experiments\summarize.py results\<session>
```

Pengujian ini bisa lama karena sembilan pemadaman backend diikuti boot kembali.
Untuk demo kelas, satu run stabil/spike sudah bisa memperlihatkan perilaku LB;
hasil pembanding sebelumnya tersedia pada `examples/benchmark-summary.csv`.

Hasil sebelumnya memakai workload `GET /`, nominal 60 detik per run, 10 user
untuk stabil/fault dan 10→40→10 untuk spike. Seluruh 18.350 request dicocokkan
antara CSV klien dan LB. Ada 31 kegagalan HTTP 502 pada fault.

Beberapa snapshot statistik Locust belum mencakup request terakhir dan empat
run mencatat error penulis statistik setelah tes selesai. Perhitungan memakai
log per-request lengkap. Dua pemulihan boot vm101 memerlukan intervensi setelah
jendela pengukuran; data hasil dicocokkan sebelum sesi dilanjutkan. `noapic`
sementara baru dipakai setelah seluruh pengukuran selesai.
