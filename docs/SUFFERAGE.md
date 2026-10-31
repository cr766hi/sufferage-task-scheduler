# Algoritma dan metrik task scheduling

Kode utama: [vm210/sufferage.py](../vm210/sufferage.py), fungsi `sufferage_plan()`.

## Model eksperimen

Task independen, semua datang bersamaan (arrival = 0), tidak dipreempt atau
dimigrasikan. Dataset tetap berisi Task ID dan jenis/ukuran pekerjaan. Matriks
ETC mengestimasi durasi eksekusi task pada setiap worker. ETC memakai median dua
`worker_elapsed_ms` setelah warmup; empat worker dikalibrasi bersamaan sebelum
batch. Kontensi nested emulation tetap memengaruhi estimasi.

## Langkah Sufferage

1. Ready time awal setiap VM = 0.
2. Untuk setiap task belum dialokasikan, hitung `CT(task,VM) = ready(VM) + ETC(task,VM)`.
3. Sufferage task = CT terbaik kedua − CT terbaik.
4. Pilih task dengan Sufferage terbesar, lalu alokasikan ke VM dengan CT terkecil.
5. Perbarui ready time VM menjadi CT task yang dialokasikan.
6. Hitung ulang seluruh kandidat yang tersisa sampai semua task terjadwal.

Tie Sufferage mengikuti urutan dataset; tie CT mengikuti urutan worker. Selisih
nol valid ketika dua pilihan sama baiknya. Setelah rencana selesai, tiap worker
mengeksekusi antrean dalam urutan alokasi, dan semua antrean berjalan paralel.

Contoh dua task dan dua worker (angka ilustrasi, bukan hasil ukur):

| Task | ETC A ms | ETC B ms | Sufferage awal ms |
|---|---:|---:|---:|
| light | 20 | 10 | 10 |
| heavy | 100 | 50 | 50 |

Heavy masuk B terlebih dahulu. Ready B = 50. CT light menjadi A=20 dan B=60,
sehingga light masuk A. Perhitungan ini diuji otomatis.

## Definisi hasil

- Arrival semua task = 0 pada saat scheduler menerima batch setelah kalibrasi.
- Waiting = start − arrival; start adalah saat scheduler mulai RPC task tersebut.
- Execution = finish − start, termasuk transport scheduler–worker.
- Turnaround = finish − arrival; sama dengan waiting + execution.
- Makespan = waktu batch dari admission sampai antrean selesai/terminal; mencakup
  planning dan persiapan snapshot resource awal, tidak mencakup kalibrasi.
- Throughput = task sukses / makespan dalam detik.
- Rata-rata waiting/turnaround dan p95 hanya task sukses; kegagalan dan skipped
  dilaporkan terpisah. Untuk batch gagal, makespan adalah durasi terminasi parsial,
  bukan durasi menyelesaikan semua task.
- Predicted makespan = finish virtual terbesar; tidak sama dengan makespan aktual.

Seluruh waktu start/finish/arrival diukur pada monotonic clock vm210 yang sama,
sehingga tidak membutuhkan sinkronisasi jam lintas VM. CPU time dan elapsed worker
adalah ukuran tersendiri di dalam VM worker. Virtual clock/emulasi dan kontensi
laptop membatasi interpretasi hasil sebagai performa mesin produksi.

Dataset 40 task: light 20 × 2 unit, medium 12 × 8 unit, heavy 8 × 24 unit,
setiap unit 1.000 iterasi PBKDF2-SHA256. Rasio kerja 1:4:12, tanpa sleep buatan.
Sufferage adalah heuristik; pengujian fungsional tidak membuktikan optimalitas.

Jika worker gagal, task aktif ditandai failed dan task antreannya yang belum
dijalankan ditandai skipped. Tidak ada rescheduling/retry tersembunyi. Timeout RPC
dapat terjadi meskipun komputasi pada worker belum berhenti.
