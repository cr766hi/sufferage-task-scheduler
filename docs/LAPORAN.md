# Laporan implementasi dan verifikasi Sufferage

## Sistem yang dijalankan

Windows menghasilkan trafik HTTP melalui Locust. vm210 menjalankan LB Sufferage
berbasis mini-batch (20 request / 75 ms). Empat VM backend menjalankan nginx untuk
identitas halaman dan worker CPU port 8080 untuk task light/medium/heavy.
Kapasitas model vm101:vm102:vm201:vm202 = 1:2:1:2. Tidak ada perpindahan VM oleh
algoritma. Host Proxmox tetap mengelola infrastruktur.

Task CPU memiliki 2/8/24 unit, masing-masing 1.000 iterasi PBKDF2-SHA256. Total kerja
dibagi ke 1 atau 2 proses sesuai kapasitas VM. Locust memilih task dengan target
proporsi 50%/30%/20%; komposisi aktual acak dan jumlahnya dapat berbeda.
Estimasi Sufferage dipelajari per jenis task dari CPU time worker. Jejak CT terbaik,
CT kedua, Sufferage, batch dan urutan alokasi tersedia dalam CSV.

## Hasil verifikasi resource terbaru

Sumber lokal: `results/pengujian 3.csv`, selesai **31-10-2026 09:13:17 WIB**.
Ini satu uji fungsi singkat, bukan benchmark lengkap tiga pengulangan per skenario.
Skenario stable, 10 user virtual, durasi rencana 15 detik; durasi aktual termasuk
penyelesaian request terakhir adalah 17.77 detik.

| Request selesai | Gagal | Rata-rata respons | P95 | Throughput | Error rate |
|---:|---:|---:|---:|---:|---:|
| 103 | 0 | 1575.88 ms | 2833.77 ms | 5.80 req/s | 0.00% |

| Task | Request | Rata-rata ms | P95 ms | vm101 | vm102 | vm201 | vm202 |
|---|---:|---:|---:|---:|---:|---:|---:|
| light | 51 | 1430.30 | 2749.57 | 5 | 22 | 3 | 21 |
| medium | 32 | 1611.47 | 2977.04 | 4 | 20 | 2 | 6 |
| heavy | 20 | 1890.18 | 2833.77 | 0 | 13 | 0 | 7 |

## Resource utilization guest VM

CPU/RAM dipantau setiap dua detik. CPU 100% berarti seluruh vCPU guest sibuk;
RAM memakai MemTotal − MemAvailable. CPU rata-rata dibobot berdasarkan selisih
counter, RAM rata-rata berdasarkan sampel berhasil. Puncak adalah maksimum yang
teramati, bukan jaminan puncak sesaat. Sampel monitoring tidak dihitung sebagai
request aplikasi. Angka hanya untuk guest, bukan CPU/RAM host atau laptop fisik.

| VM | CPU rata-rata % | CPU puncak % | RAM rata-rata % | RAM puncak % | Sampel OK/gagal |
|---|---:|---:|---:|---:|---:|
| vm101 | 18.85 | 32.34 | 24.18 | 24.19 | 9/0 |
| vm102 | 73.62 | 97.40 | 30.52 | 30.57 | 9/0 |
| vm201 | 12.08 | 34.84 | 24.05 | 24.07 | 9/0 |
| vm202 | 26.69 | 39.87 | 30.17 | 30.22 | 9/0 |
| vm210 | 88.16 | 100.00 | 19.72 | 19.72 | 9/0 |

CPU LB vm210 mencapai puncak 100% dan rata-rata sekitar 88%. Ini menunjukkan
kemungkinan keterbatasan LB pada lingkungan emulasi; belum membuktikan penyebab
tunggal latency. vCPU, memori, cluster dan konfigurasi jaringan tidak diubah.
20 task berat pada run ini masuk vm102/vm202. Ini pengamatan run tersebut,
bukan aturan bahwa task berat selalu dialokasikan ke kedua VM itu.

## Pemeriksaan yang selesai

- Delapan tes kode lolos: scheduler/CT, proxy, checksum pembagian kerja CPU,
  estimasi per task, rumus CPU/RAM, reset counter, dan sampel hilang.
- Lima endpoint resource aktif; uji integrasi menghasilkan satu CSV dengan
  ringkasan aplikasi dan kelima ringkasan resource.
- Service worker dan LB berstatus started dan terdaftar pada runlevel default.
- 21 file terpasang diverifikasi terhadap sumber repo dengan newline LF;
  rinciannya ada di `examples/source-provenance.json`.
- Tabel HTML diperiksa secara visual. Password, token, CSV mentah, dan HTML hasil
  lokal tidak dimasukkan ke GitHub; kode dan ringkasan laporan tersedia di repo.

## Batas interpretasi dan langkah evaluasi berikutnya

Benchmark historis 27 run di `examples/benchmark-summary.csv` memakai halaman
nginx seragam. Hasil itu tidak dapat diperlakukan sebagai pembanding langsung
untuk task CPU baru. Pengujian 1/2 lokal juga belum mempunyai metrik resource;
angkanya dibiarkan tidak tersedia. Perbedaan pengujian 2 dan 3 tidak mengukur
overhead pemantauan secara terkontrol.

Untuk laporan eksperimen akhir, jalankan stable, spike dan fault masing-masing
minimal tiga kali dengan durasi dan workload yang sama. Laporkan mean/p95 latency,
throughput, error rate, pembagian task dan resource per VM. Workload closed-loop,
kontensi satu laptop, nested emulation dan overhead monitoring memengaruhi hasil.
Resource dipakai untuk evaluasi, bukan input baru yang mengganti rumus Sufferage.
Belum dilakukan benchmark CPU tiga algoritma atau fault ulang untuk versi ini.

Cara demo langsung: [DEMO_SINGKAT.md](DEMO_SINGKAT.md).
Rumus resource: [RESOURCE.md](RESOURCE.md). Penjelasan scheduler: [SUFFERAGE.md](SUFFERAGE.md).
