# Instalasi scheduler

Pada Windows, dari akar repo:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r windows\requirements.txt
.\.venv\Scripts\python.exe scripts\install_task_workers.py
.\.venv\Scripts\python.exe scripts\install_scheduler.py
```

Installer meminta password melalui prompt tersembunyi. Worker stdlib pada :8080
dan aiohttp scheduler pada vm210 :80. Tidak mengubah nginx, bridge, IP, disk atau
konfigurasi cluster. Installer scheduler menghentikan layanan `sufferage-lb` lama
dan menghapusnya dari runlevel default; kode/log lama tetap ada untuk arsip.

Service baru bernama `task-scheduler`, enabled pada runlevel default. Pada vm210:

```sh
rc-service task-scheduler status
rc-update show default
```

Jangan restart scheduler saat batch aktif. Hasil batch selesai disimpan dalam
`/var/log/sufferage-scheduler/batch-*/result.json`; log per task ada pada `tasks.csv`.
Batch yang terputus karena crash saat berjalan tidak otomatis dilanjutkan.
API menolak lebih dari satu batch aktif agar antrean worker tidak tumpang tindih.
Kalibrasi diulang setelah restart scheduler; hasil batch selesai tetap dapat diambil.
