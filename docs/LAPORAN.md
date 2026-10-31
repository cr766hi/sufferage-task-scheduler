# Laporan verifikasi task scheduling Sufferage

## Ruang lingkup revisi

Implementasi aktif adalah scheduler batch statis, bukan eksperimen trafik web.
Windows mengirim dataset 40 task independen: 20 light, 12 medium, 8 heavy (seed 42).
vm210 membuat rencana Sufferage lengkap dari matriks ETC terukur, kemudian
mengeksekusi empat antrean worker secara paralel. Di dalam satu worker task logis
tidak tumpang tindih. Worker dua vCPU memakai dua proses untuk satu task.
Layanan lama sufferage-lb telah dihentikan dan dinonaktifkan dari runlevel default.
Layanan baru task-scheduler aktif dan autostart; hostname/IP/cluster tetap sama.

## Hasil tiga pengulangan nyata

Dataset dan calibration ID sama pada semua run di bawah. Kalibrasi dilakukan
sebelum batch pertama; dua pengulangan memakai --reuse-calibration. Semua hasil
berasal dari VM sebenarnya, bukan angka ilustrasi. Hasil HTTP lama tidak dipakai.

| Ulang | Task selesai | Gagal/skipped | Makespan s | Rata-rata waiting ms | Rata-rata turnaround ms | Throughput task/s |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 40/40 | 0/0 | 5.416 | 2912.41 | 3300.74 | 7.39 |
| 2 | 40/40 | 0/0 | 5.080 | 2626.89 | 3052.20 | 7.87 |
| 3 | 40/40 | 0/0 | 4.947 | 2396.32 | 2786.94 | 8.09 |

Rata-rata makespan tiga run: **5.147 s**. Semua 120 eksekusi task selesai sukses.

| Worker | Task dialokasikan per run |
|---|---:|
| vm101 | 12 |
| vm102 | 9 |
| vm201 | 9 |
| vm202 | 10 |

Alokasi sama pada ketiga run karena dataset, ETC dan tie-break sama; waktu aktual
berbeda karena overhead dan kontensi emulasi. Jumlah alokasi bukan kuota pemerataan.
Task berbeda ukuran, sehingga jumlah task sama tidak berarti beban CPU sama.

## Matriks ETC yang dipakai

Median dua waktu eksekusi worker setelah warmup, dalam ms. Worker dikalibrasi
bersamaan sehingga estimasi mencerminkan kondisi kontensi saat pengukuran.

| Jenis | vm101 | vm102 | vm201 | vm202 |
|---|---:|---:|---:|---:|
| light | 136.44 | 105.62 | 116.23 | 90.53 |
| medium | 220.24 | 179.32 | 170.88 | 163.09 |
| heavy | 823.50 | 217.16 | 685.15 | 264.20 |

Predicted makespan dari ETC sekitar 1,64 s, sedangkan aktual sekitar 5 s. Prediksi
belum memasukkan seluruh biaya RPC, planning, monitoring, dan perubahan kontensi.
Perbedaan tersebut dilaporkan; estimasi tidak disamakan dengan hasil pengukuran.

## Resource guest: cakupan pengukuran

Setiap run singkat ini menghasilkan dua snapshot berhasil per VM, sehingga hanya
satu interval CPU valid per VM per run. CPU di bawah menggabungkan tiga interval
secara berbobot ticks; puncak adalah maksimum interval, bukan puncak instan seluruh
batch. RAM adalah rata-rata snapshot valid. Untuk resource yang lebih representatif,
gunakan dataset demo120.csv atau dataset lebih besar dan ulangi pengujian.

| VM | CPU rata-rata % | CPU puncak % | RAM rata-rata % | Interval CPU valid total |
|---|---:|---:|---:|---:|
| vm101 | 40.03 | 46.08 | 19.27 | 3 |
| vm102 | 33.00 | 37.43 | 22.43 | 3 |
| vm201 | 46.38 | 50.76 | 19.52 | 3 |
| vm202 | 26.32 | 29.89 | 22.45 | 3 |
| vm210 | 71.26 | 75.00 | 19.56 | 3 |

## Bukti dan keterbatasan

- Empat tes kode lulus: pemilihan global Sufferage terbesar, reservasi CT, validasi
  task/reset resource, dan integrasi batch termasuk metrik serta penyimpanan/resume.
- Uji nyata memverifikasi waiting + execution = turnaround, CT kedua − CT terbaik
  = Sufferage, serta antrean per worker tanpa tumpang tindih.
- 23 file terpasang worker/scheduler cocok dengan sumber repo (normalisasi LF).
  Rincian ada pada [source-provenance.json](../examples/source-provenance.json).
- Semua resource guest teramati; timeout/error tetap dicatat, tidak dijadikan nol.
- Dataset 40 task adalah dataset sintetis CPU dengan urutan tetap, bukan dataset
  publik atau replay trafik pengguna. Pekerjaan CPU benar-benar dikerjakan worker.
- Tidak ada pembandingan dengan algoritma lain untuk versi batch ini, sehingga
  hasil tidak membuktikan Sufferage paling optimal. Fault/rescheduling bukan bagian
  evaluasi ini; worker gagal menghasilkan task failed/skipped secara eksplisit.
- Seluruh host/guest berjalan pada satu laptop dengan nested emulation. Waktu
  start/finish diukur dari monotonic clock scheduler yang sama, bukan gabungan
  jam dinding worker. Kalibrasi berada di luar makespan.

CSV mentah tersimpan lokal di results/pengujian 5.csv, 6.csv dan 7.csv. Repo memuat
kode, dataset, definisi metrik dan laporan ringkas; tidak memuat password atau token.
Cara demo langsung, termasuk SSH: [DEMO.md](DEMO.md).
