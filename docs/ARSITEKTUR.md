# Arsitektur task scheduler

Satu laptop Windows 16 GB menjalankan dua host Proxmox nested pada VirtualBox.
Cluster `datacenter-lb` dan seluruh IP/hostname tetap seperti konfigurasi semula;
nama cluster tersebut hanya identitas infrastruktur.

| Mesin | IP | Peran aktif |
|---|---|---|
| Windows | 192.168.56.1 | Dataset CSV, script submit, tabel hasil |
| pve1 | 192.168.56.11 | Proxmox, menjalankan VM 101 dan 102 |
| pve2 | 192.168.56.12 | Proxmox, menjalankan VM 201, 202 dan 210 |
| vm101 | 192.168.56.21 | Worker :8080, 512 MB, 1 vCPU/proses CPU |
| vm102 | 192.168.56.22 | Worker :8080, 512 MB, 2 vCPU/proses CPU |
| vm201 | 192.168.56.31 | Worker :8080, 512 MB, 1 vCPU/proses CPU |
| vm202 | 192.168.56.32 | Worker :8080, 512 MB, 2 vCPU/proses CPU |
| vm210 | 192.168.56.10 | Scheduler :80, 1024 MB, 1 vCPU |

Host pve1/pve2 tidak menjalankan kode algoritma. Scheduler tidak mengubah VM,
memindahkan VM, atau membagi vCPU host. HTTP digunakan sebagai RPC kontrol task.
Port 80 vm210 tidak meneruskan trafik web pengguna. Nginx pada worker tetap
melayani halaman identitas di port 80, tetapi tidak menjadi target eksperimen.

## Lokasi program

| VM | Lokasi | Sumber repo |
|---|---|---|
| vm210 | `/opt/sufferage-scheduler/scheduler.py` | `vm210/scheduler.py` |
| vm210 | `/opt/sufferage-scheduler/sufferage.py` | `vm210/sufferage.py` |
| vm210 | `/etc/init.d/task-scheduler` | `vm210/openrc/task-scheduler` |
| vm210 | `/usr/local/sbin/run-task-scheduler` | `vm210/openrc/run-task-scheduler` |
| worker | `/opt/task-worker/worker.py` | `backends/worker/worker.py` |
| semua guest | `vm_metrics.py` pada direktori program | `monitoring/vm_metrics.py` |

Setiap worker mengeksekusi satu task logis pada satu waktu sesuai antrean scheduler.
Untuk task di VM dua vCPU, unit perhitungan dibagi ke dua proses sehingga total
kerja/checksum sama dengan VM satu vCPU. Scheduler tetap memakai satu ready time
per VM; ETC sudah mengukur percepatan nyata masing-masing worker.
