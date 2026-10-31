# Cara kerja Sufferage dalam kode

Kode inti: [vm210/lb.py](../vm210/lb.py), fungsi `sufferage_plan()`.

## Langkah penjadwalan

1. Maksimal 20 request atau jendela pengumpulan 75 ms.
2. Pilih hanya backend yang sehat.
3. Untuk tiap request, hitung pada setiap backend:

   `CT = max(now, ready_time_backend) + estimated_work / capacity`

4. `sufferage = CT_terbaik_kedua - CT_terbaik`.
5. Request dengan Sufferage terbesar dipilih, ditugaskan ke backend dengan CT
   terbaik, dan ready time virtual backend diperbarui.
6. Hitung ulang request yang tersisa sampai batch habis, kemudian forward HTTP.

Contoh ilustrasi dua backend, bukan data hasil benchmark:

| Request | CT A, bobot 1 | CT B, bobot 2 | Sufferage |
|---|---:|---:|---:|
| Kerja 20 ms | 20 | 10 | 10 |
| Kerja 100 ms | 100 | 50 | 50 |

Request besar lebih dulu ke B. Ready time B menjadi 50 ms. CT request kecil
dihitung ulang: A = 20 ms, B = 50 + 10 = 60 ms, sehingga request kecil ke A.

## Estimasi dan kondisi nyata

Task CPU dibedakan melalui path: `/task/light`, `/task/medium`, `/task/heavy`.
Profil bersama ada di [workload/task_profiles.json](../workload/task_profiles.json):

| Jenis | Unit CPU | Iterasi PBKDF2 total | Estimasi awal kapasitas 1 | Campuran Locust |
|---|---:|---:|---:|---:|
| light | 2 | 2.000 | 50 ms | 50% |
| medium | 8 | 8.000 | 200 ms | 30% |
| heavy | 24 | 24.000 | 600 ms | 20% |

Estimasi awal adalah parameter, bukan waktu respons yang dijamin. Setelah respons
CPU sukses, LB mempelajari estimasi masing-masing path melalui EWMA:

`baru = 0.8 × lama + 0.2 × jumlah_waktu_CPU_proses_worker`

Worker melaporkan `X-Worker-CPU-Ms`, jumlah CPU time proses yang mengerjakan unit
PBKDF2. Ini mengecualikan waktu menunggu antrean worker; bukan metrik utilisasi CPU.
Untuk halaman statis `/`, estimasi awal tetap 20 ms dan observasi memakai
`durasi_upstream × bobot_backend`. Cadangan ini juga dipakai bila header CPU tidak ada.

Worker memecah satu task menjadi 1 atau 2 bagian sesuai kapasitas backend. Total
kerja dan checksum tetap sama untuk jenis task yang sama di semua VM. Tidak ada
`sleep` untuk memperlambat request. Kapasitas 1:2:1:2 tetap model berdasarkan vCPU;
emulasi, overhead proses/jaringan, dan kontensi laptop membuat percepatan aktual
tidak harus tepat dua kali. `ready_time` adalah reservasi virtual, bukan antrean CPU aktual.

Header dan CSV menyertakan `estimated_work_ms`, `sufferage_ms`, `best_ct_ms`,
`second_ct_ms`, `batch_id`, dan `assignment_order`. CT relatif terhadap waktu
penjadwalan batch. Nilai dihitung ulang setiap alokasi. Dua backend terbaik dapat
memiliki CT yang sama sehingga Sufferage nol; ini sah, termasuk pada task berat.
Task berat tidak selalu dipilih lebih dulu atau selalu masuk backend bobot 2:
keputusan mengikuti selisih CT dan reservasi yang ada.

## Fungsi-fungsi yang perlu ditunjukkan

| Fungsi/kelas | Peran |
|---|---|
| `Backend` | URL, bobot, kesehatan, request aktif, ready time |
| `Job` | Request yang menunggu jadwal |
| `handle()` | Menerima HTTP dan memasukkan job ke antrean |
| `scheduler()` | Membentuk batch dan memilih algoritma |
| `sufferage_plan()` | Memilih urutan request/backend berdasarkan selisih CT |
| `dispatch()` / `forward()` | Memproses HTTP ke backend dan mengembalikan respons |
| `probe()` / `health_loop()` | Health check backend |
| `record()` | CSV request |

Source mempertahankan mode pembanding yang dipakai pada benchmark agar kode
penelitian dapat ditelusuri. Layanan OpenRC dan wrapper operasional selalu
menjalankan argumen `sufferage`; demo tidak perlu mengganti algoritma.

## Batasan yang perlu dijelaskan

- Task CPU saat ini memiliki rasio kerja 1:4:12; seluruh task memakai jenis komputasi yang sama. Belum ada workload I/O atau replay trafik produksi.
- Waktu batching masuk ke latency klien. Batching tidak menjamin respons lebih cepat.
- Bobot kapasitas belum dikalibrasi melalui benchmark CPU nyata.
- Jumlah request per VM dan jumlah request/bobot punya interpretasi berbeda.
- CSV menyimpan CT terbaik/kedua dan Sufferage saat terpilih, tetapi belum seluruh matriks kandidat setiap langkah.
- Satu VM LB belum memiliki redundansi; health check menangani kegagalan backend.
- Pada benchmark historis halaman nginx seragam, Round Robin memberi mean latency terendah;
  Sufferage lebih mendekati pembagian bobot pada stabil/spike. Lihat contoh ringkasan.
