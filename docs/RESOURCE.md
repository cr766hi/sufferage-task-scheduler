# Pengukuran resource utilization

## Cakupan dan pengambilan sampel

Windows Locust mengambil metrik seluruh guest pada empat backend dan vm210
setiap dua detik selama tes. HTTP dijalankan langsung ke endpoint metrik, di luar
`HttpUser`, sehingga tidak menambah request, failures atau throughput aplikasi.
Pemantauan tetap menggunakan sedikit CPU/jaringan dan masuk pengukuran resource.
Sumber collector: `windows/resource_monitor.py`; pembaca Linux bersama:
`monitoring/vm_metrics.py`. Tidak ada dependensi pip baru atau perubahan nginx.

| VM | Endpoint |
|---|---|
| vm101 | `http://192.168.56.21:8080/metrics` |
| vm102 | `http://192.168.56.22:8080/metrics` |
| vm201 | `http://192.168.56.31:8080/metrics` |
| vm202 | `http://192.168.56.32:8080/metrics` |
| vm210 | `http://192.168.56.10/__lb/metrics` |

Modul Linux dipasang sebagai `/opt/task-worker/vm_metrics.py` di backend dan
`/opt/sufferage-lb/vm_metrics.py` di LB. Layanan yang sudah ada mengekspos endpoint;
tidak ada daemon pemantau tambahan. Installer masing-masing menyalin modul ini.

## Definisi metrik

- CPU total ticks = user + nice + system + idle + iowait + irq + softirq + steal.
- CPU busy ticks = user + nice + system + irq + softirq.
- CPU persen interval = `100 × Δbusy / Δtotal`. Idle, iowait dan steal tidak
  dianggap CPU mengeksekusi pekerjaan. guest/guest_nice tidak dijumlah ulang.
- Angka CPU dinormalisasi ke seluruh vCPU: 100% berarti semua vCPU VM sibuk;
  satu vCPU penuh pada VM dua vCPU menghasilkan sekitar 50%.
- CPU rata-rata per tes = `100 × ΣΔbusy / ΣΔtotal`, bukan rata-rata persen
  yang memberi bobot sama pada interval tidak sama. Puncak = persen interval terbesar.
- RAM terpakai = `MemTotal − MemAvailable`; persen = terpakai / total × 100.
  Ini estimasi RAM yang tidak tersedia, bukan RSS worker dan bukan seluruh cache
  dianggap terpakai. Satuan MiB = kB dari procfs / 1024.
- Rata-rata RAM adalah rata-rata sampel berhasil. Puncak RAM adalah maksimum
  snapshot yang berhasil, sehingga lonjakan singkat antar sampel bisa terlewat.

Rujukan primer: [dokumentasi Linux procfs](https://www.kernel.org/doc/html/latest/filesystems/proc.html?highlight=meminfo).

## Data hilang, reset, dan batasan

Sampel pertama hanya menyediakan counter baseline dan RAM; CPU persen belum ada.
Collector memeriksa boot ID serta counter monotonic. Setelah VM tidak terjangkau
atau reboot, baseline direset. CPU baru dihitung setelah dua snapshot valid lagi.
Timeout/error direkam sebagai sampel gagal dengan angka resource kosong. Jangan
mengartikan VM mati sebagai CPU/RAM 0%. Tabel menampilkan jumlah OK/gagal dan
durasi CPU teramati agar kekurangan cakupan terlihat. Endpoint lambat dapat
membuat jarak sampel lebih dari dua detik; selisih waktu aktual tetap dicatat.
Pengujian yang sangat singkat mungkin belum memiliki interval CPU valid.

Nilai berasal dari guest Alpine emulasi, bukan host pve1/pve2 atau Windows.
Pengukuran mencakup OS, nginx, worker, dan overhead pemantauan di guest tersebut.
CPU utilization berbeda dari `worker_cpu_ms`, yang merupakan CPU time satu task.
Resource adalah metrik evaluasi, bukan input tambahan untuk mengubah keputusan
Sufferage. Workload dan algoritma tetap sama saat membandingkan pengujian.

## Output

Satu `results/pengujian N.csv` menyimpan request, ringkasan aplikasi, sampel resource
dan lima ringkasan resource per VM. `hasil_pengujian.html` menampilkan tabel terpisah
agar kolom aplikasi tetap mudah dibaca. Hasil lama tidak direkonstruksi atau diisi
dengan perkiraan resource. Restart proses Locust untuk memuat collector baru.
