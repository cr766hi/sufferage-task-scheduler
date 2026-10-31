# Laporan revisi ETC v2 dan efisiensi Sufferage

## Perubahan aktif

1. ETC v2 memakai median **7 sampel RPC** per jenis task dan worker, diukur pada
   monotonic clock scheduler. Warmup mencakup seluruh jenis task; urutan campuran
   berotasi dan monitoring resource aktif selama kalibrasi. Biaya transport masuk
   estimasi, sesuai definisi execution_ms pada hasil batch.
2. Planner mengelompokkan task dengan baris ETC identik. Keputusan tetap Sufferage
   yang sama: max selisih CT terbaik/kedua, dengan tie-break urutan dataset/worker.
   Differential test hingga 500 task memastikan seluruh alokasi dan CT identik
   dengan perhitungan lengkap. Optimasi mengurangi kerja planning di vm210.
3. CSV/HTML menambah MAPE prediksi, total unit kerja, waktu selesai worker, jeda
   akhir, versi ETC dan timeline task nyata. CPU/RAM tetap hasil ukur, tanpa kuota
   pemerataan atau angka yang dipaksakan.

## Hasil normal pada dataset 120 task

Dataset sama: 60 light, 36 medium, 24 heavy, seed 42. Seluruh run v2 normal di
bawah memakai calibration ID yang sama; kalibrasi berada di luar makespan.

| Ulang | Selesai | Makespan s | Planning ms | MAPE execution % | Selisih selesai worker s |
|---|---:|---:|---:|---:|---:|
| 1 | 120/120 | 14.271 | 70.65 | 29.46 | 1.411 |
| 2 | 120/120 | 13.172 | 29.03 | 29.09 | 1.366 |
| 3 | 120/120 | 14.196 | 114.40 | 31.37 | 0.885 |

Jumlah run normal: **3**, seluruh **360 task** berhasil.
Rata-rata makespan **13.880 s**, planning **71.36 ms**,
MAPE **29.97%**, dan selisih selesai worker **1.221 s**.

## Pembanding catatan v1

Ini perbandingan observasional pada laptop yang sama, bukan eksperimen A/B
terkontrol: satu catatan v1 dibanding beberapa run v2 pada waktu berbeda.
Kontensi dan kondisi setelah reboot dapat berbeda, sehingga angka tidak cukup
untuk mengklaim peningkatan yang selalu terjadi.

| Versi | Makespan s | Planning ms | MAPE execution % | Selisih selesai worker s |
|---|---:|---:|---:|---:|
| v1 (pengujian 1.csv) | 17.642 | 2944.77 | 58.11 | 5.116 |
| v2 rata-rata run normal | 13.880 | 71.36 | 29.97 | 1.221 |

MAPE = rata-rata `abs(execution_ms - ETC) / execution_ms × 100%`, hanya task sukses.
Execution mencakup RPC, bukan CPU time murni. Jeda akhir worker yang lebih kecil
menunjukkan antrean berakhir lebih berdekatan pada pengukuran tersebut; ini tidak
menjamin utilisasi CPU sama atau jadwal optimal.

## Gangguan yang tidak disembunyikan

Pengulangan lain terputus ketika vm101 dan vm102 kehilangan konektivitas.
Task mengembalikan `TimeoutError:` dan resource kedua worker juga gagal diambil.
Diagnostik sesudahnya menemukan host pve1 baru reboot (uptime sekitar dua menit)
dan kedua guest stopped. Agent tidak menjalankan shutdown/restart host. Penyebab
reboot belum ditetapkan; tidak ada perubahan cluster, IP, bridge atau HA.

Batch `batch-20261031T052431Z-114d74`: 69 task sukses, 2 failed, 49 skipped, durasi terminasi 61.609 s.

Hasil tersebut tetap berada di CSV/HTML dengan status completed_with_errors.
Run terganggu ini tidak dimasukkan ke rata-rata run normal, dan tidak disebut
berhasil. Guest yang stopped dinyalakan kembali; host tidak dimatikan.

Run normal ketiga dilakukan setelah pve1 pulih dan seluruh jenis task di-warmup kembali. ETC tetap sama, tetapi kondisi setelah reboot bukan kondisi eksperimen yang sepenuhnya identik.

## Batasan yang tetap berlaku

- CV sampel kalibrasi tertinggi pada sesi ini **39.58%**; variasi emulasi
  masih nyata. Median tujuh sampel meningkatkan ketahanan terhadap sebagian
  outlier, bukan jaminan ETC tepat pada setiap task.
- Predicted makespan tetap bisa berbeda dari aktual. Versi ini menambahkan
  execution_phase_seconds dan predicted_batch_makespan_seconds agar biaya awal
  planning/persiapan tidak tercampur dengan prediksi antrean virtual.
- CPU persen dinormalisasi terhadap seluruh vCPU guest. Task lebih sedikit bisa
  mempunyai lebih banyak unit kerja. Tidak ada target memaksa semua CPU sama.
- Resource disampel tiap dua detik, puncak adalah puncak interval/snapshot teramati.
- Sufferage adalah heuristik; belum ada pembuktian optimalitas atau perbandingan
  algoritma lain pada evaluasi ini. Tidak ada retry/rescheduling tersembunyi.
- Enam tes otomatis lolos: validasi task, reservasi CT, eksekusi/hasil/resume,
  reset resource, tujuh sampel RPC, serta ekuivalensi planner termasuk tie.

Cara demo dan SSH: [DEMO.md](DEMO.md). Rumus algoritma: [SUFFERAGE.md](SUFFERAGE.md).

## Penyajian visual hasil

Laporan HTML lokal kini menampilkan 12 grafik per batch: komposisi task, status,
jenis task per worker, unit kerja per worker, waiting/turnaround per jenis, waktu
selesai worker, ETC versus aktual, prediksi versus durasi batch, CPU, RAM, kurva
CPU sepanjang eksekusi, dan nilai Sufferage sepanjang urutan alokasi. Grafik
makespan dan throughput antar-pengujian muncul jika terdapat lebih dari satu CSV.

Angka grafik berasal dari CSV yang sama dengan tabel. Tidak ada pengujian baru
atau perubahan hasil lama untuk menghasilkan grafik ini. Tabel jejak CT dan
waktu eksekusi tetap tersedia untuk memeriksa keputusan algoritma. Kurva Sufferage
bisa naik/turun karena ready time diperbarui setiap keputusan. Grafik resource
menampilkan pengukuran guest dan tidak menganggap sampel hilang sebagai nol.
Cara membuat ulang HTML dan urutan penjelasan demo ada pada [DEMO.md](DEMO.md).

## Laporan singkat kelompok

[Laporan Word kelompok](Laporan_Task_Scheduler_Sufferage.docx) menyajikan
ringkasan 7 halaman dengan 9 gambar/grafik. Laporan ini membahas batch 240 task
`batch-20261031T123432Z-28cd6a`, calibration ID `etc-0621511b`, dengan 240 task
selesai, makespan 31,24 detik, dan throughput 7,68 task/detik. Ini sesi yang berbeda
dari catatan pengulangan 120 task di atas. Grafik merupakan screenshot HTML hasil.
