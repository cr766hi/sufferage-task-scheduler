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
Halaman indeks masing-masing berisi nama VM. Ini konten statis, tanpa program
Python pekerjaan CPU. Algoritma dan estimasi Sufferage hanya ada di vm210.

File OS pendukung nginx tetap disediakan paket Alpine. Folder ini adalah rekaman
file relevan yang digunakan, bukan image lengkap atau installer sistem operasi.
