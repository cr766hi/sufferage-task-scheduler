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

Estimasi awal adalah 20 ms pada kapasitas satu, dipelajari per path dengan EWMA:

`baru = 0.8 × lama + 0.2 × (durasi_upstream × bobot_backend)`

Durasi upstream mencakup transaksi HTTP dan waktu tunggu. Ini bukan durasi CPU
murni. `ready_time` adalah prediksi/reservasi virtual; LB tidak membaca antrean
CPU backend. Bobot 1:2:1:2 adalah parameter model berdasarkan vCPU.

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

- Request saat ini sama-sama `GET /` halaman kecil; variasi biaya pekerjaan minim.
- Waktu batching masuk ke latency klien. Batching tidak menjamin respons lebih cepat.
- Bobot kapasitas belum dikalibrasi melalui benchmark CPU nyata.
- Jumlah request per VM dan jumlah request/bobot punya interpretasi berbeda.
- CSV belum menyimpan matriks CT atau nilai Sufferage tiap kandidat.
- Satu VM LB belum memiliki redundansi; health check menangani kegagalan backend.
- Dalam benchmark sebelumnya, Round Robin memberi mean latency terendah;
  Sufferage lebih mendekati pembagian bobot pada stabil/spike. Lihat contoh ringkasan.
