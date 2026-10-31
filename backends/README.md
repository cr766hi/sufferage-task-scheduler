# File aktual pada VM backend

Folder vm101, vm102, vm201, vm202 berisi salinan read-only dari konfigurasi yang
dipakai nginx pada VM terkait. Struktur folder mengikuti path asal di guest.
Pemetaan lengkap ada di [inventory.json](inventory.json).

Contoh vm101:

```text
vm101/
├── etc/nginx/nginx.conf
├── etc/nginx/mime.types
├── etc/nginx/http.d/default.conf
└── var/www/localhost/htdocs/index.html
```

`default.conf` membuka port 80 dan root `/var/www/localhost/htdocs`.
Halaman indeks masing-masing berisi nama VM. Konten nginx tetap statis.
Worker CPU terpisah berjalan di port 8080; sumbernya ada di `worker/`. Algoritma dan estimasi Sufferage hanya ada di vm210.

File OS pendukung nginx tetap disediakan paket Alpine. Folder ini adalah rekaman
file relevan yang digunakan, bukan image lengkap atau installer sistem operasi.

## Worker CPU (baru)

`worker/worker.py` menggunakan Python stdlib dan ProcessPoolExecutor, tanpa
dependensi pip. Task memiliki 2/8/24 unit, masing-masing 1.000 iterasi PBKDF2-SHA256.
Kerja dibagi ke 1 atau 2 proses sesuai kapasitas VM, tanpa sleep. Checksum hasil
identik lintas backend. `GET /health` tidak menjalankan komputasi task.

Installer Windows `scripts/install_task_workers.py` memasang Python Alpine bila
belum tersedia, menyalin worker dan profil, serta mengaktifkan service OpenRC
`task-worker`. Tidak mengubah konfigurasi nginx. Lokasi runtime ada pada inventory.
