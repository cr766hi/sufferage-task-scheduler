# Instalasi kode dan layanan

## Windows

Pada akar repo:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r windows\requirements.txt
```

Dependensi Windows: Locust 2.47.0 dan Paramiko 5.1.0. Script tidak memuat password;
installer/runner meminta kredensial melalui prompt tersembunyi.

## Worker CPU di backend

Worker telah dipasang pada keempat backend lab dan aktif di runlevel default.
Untuk memasang pada clone lab yang sama dari Windows:

```powershell
.\.venv\Scripts\python.exe scripts\install_task_workers.py
```

Installer meminta password melalui prompt tersembunyi, memasang Python lewat
`apk add --no-cache python3` jika belum ada, lalu memasang service `task-worker`.
Worker port 8080 berjalan terpisah dari nginx port 80. Tidak ada konfigurasi nginx
yang diubah. Periksa melalui `http://<IP-backend>:8080/health` atau pada backend:

```sh
rc-service task-worker status
rc-update show default
```

## vm210 yang sudah dikonfigurasi

Layanan Sufferage sudah dipasang di lab ini. Untuk demo biasa, cukup cek health;
tidak perlu install ulang atau menjalankan Python LB manual.

Jika memang ingin memasang ulang dari clone repo:

```powershell
.\.venv\Scripts\python.exe scripts\install_vm210.py --host 192.168.56.10
```

Installer hanya terhubung ke vm210. Prasyaratnya Alpine dengan Python, aiohttp,
SSH root, dan OpenRC. Installer mengunggah kode repo, menyimpan cadangan file
layanan yang sudah ada dengan akhiran `.before-install`, menghentikan layanan
Sufferage yang dikelolanya jika aktif, lalu memasang dan memulai layanan.
Layanan lain pada port 80 harus ditangani terlebih dahulu; installer tidak
menghentikan proses port 80 secara acak.

Pada Alpine lab 3.24, dependensi sebelumnya dipasang dengan:

```sh
apk add --update-cache --repository https://dl-cdn.alpinelinux.org/alpine/v3.24/community py3-aiohttp
```

Versi aiohttp yang diuji adalah 3.13.5. URL repository itu mengikuti versi Alpine
lab; jangan mencampur repository versi lain pada instalasi Alpine yang berbeda.

## File runtime vm210

```text
/opt/sufferage-lb/lb.py
/opt/sufferage-lb/vm_metrics.py
/opt/sufferage-lb/task_profiles.json
/etc/init.d/sufferage-lb
/usr/local/sbin/run-sufferage-lb
/var/log/sufferage-lb/service.log
/var/log/sufferage-lb/error.log
/var/log/sufferage-lb/run-<waktu>-<acak>/requests.csv
```

OpenRC memakai `supervise-daemon`, dependency jaringan/filesystem, dan runlevel
`default`. Wrapper selalu menjalankan `sufferage --port 80`. Direktori CSV unik
dibuat setiap kali proses mulai agar restart tidak menimpa data sebelumnya.

```sh
rc-service sufferage-lb status
rc-service sufferage-lb restart
rc-service sufferage-lb stop
rc-service sufferage-lb start
rc-update show default
```

Service start dan restart telah diuji pada vm210. Cold reboot penuh VM tidak
dilakukan saat pemasangan autostart. Autostart guest di Proxmox dan VirtualBox
merupakan pengaturan terpisah; repo ini tidak mengubahnya.

## Backend dan host

Backend melayani nginx untuk halaman identitas dan worker CPU untuk variasi task Locust. Salinan konfigurasi aktual ada dalam `backends/`. Jangan menyalin seluruh
folder ke VM lain tanpa menyesuaikan identitas dan memeriksa konfigurasinya.
Untuk memeriksa konfigurasi tanpa reload:

```sh
nginx -t
```

Repo tidak mengotomatisasi cluster, bridge, hostname, IP, atau disk Proxmox.
Pemetaan host dan guest ada pada [ARSITEKTUR.md](ARSITEKTUR.md).
