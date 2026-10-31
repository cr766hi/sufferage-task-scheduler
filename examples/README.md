# Contoh output

`lb-request.csv` dan `client-request.csv` berisi dua request nyata dari satu run
Sufferage sebelumnya. Request ID menghubungkan pengamatan klien dan LB.
`response_time_ms` kedua file memiliki titik pengukuran berbeda: Windows
end-to-end versus waktu internal LB.

`benchmark-summary.csv` adalah ringkasan 27 run pembanding sebelumnya, tiga
pengulangan tiap algoritma dan skenario. Ini hasil pengukuran, bukan dataset input.
Kolom imbalance jumlah request/bobot membantu membaca kapasitas heterogen.

CSV mentah lengkap, log sistem, disk VM, dan kredensial tidak diunggah ke repo.
Pengujian demo baru menghasilkan file dalam `results/`, yang diabaikan Git.

`source-provenance.json` memverifikasi 21 file terpasang pada worker keempat backend
dan LB vm210 terhadap sumber repo dengan newline LF. Ringkasan benchmark di folder
ini tetap memakai workload nginx seragam historis, bukan task CPU baru.
