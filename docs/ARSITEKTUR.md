# Isi host dan setiap VM

## Lapisan infrastruktur

```text
Laptop fisik Windows, 16 GB RAM
└── VirtualBox
    ├── pve1: Proxmox VE, 4 GB RAM, 4 vCPU
    │   ├── VM 101: vm101, nginx, 512 MB, 1 vCPU
    │   └── VM 102: vm102, nginx, 512 MB, 2 vCPU
    └── pve2: Proxmox VE, 4 GB RAM, 4 vCPU
        ├── VM 201: vm201, nginx, 512 MB, 1 vCPU
        ├── VM 202: vm202, nginx, 512 MB, 2 vCPU
        └── VM 210: vm-lb, Python LB, 1024 MB, 1 vCPU
```

Cluster Proxmox bernama `datacenter-lb`, memiliki satu datacenter logis dan dua
node. Keduanya berada pada laptop fisik yang sama. VM Alpine memakai emulasi
tanpa akselerasi KVM, sehingga boot dan waktu respons dapat lambat.

| Mesin | IP | Program / file | Peran |
|---|---|---|---|
| Windows | 192.168.56.1 | `windows/locustfile.py`, `demo_locust.ps1` | Membuat beban dan mengukur respons klien |
| pve1 | 192.168.56.11 | Proxmox VE; UI HTTPS port 8006 | Mengelola vm101 dan vm102 |
| pve2 | 192.168.56.12 | Proxmox VE; UI HTTPS port 8006 | Mengelola vm201, vm202, vm210 |
| vm101 | 192.168.56.21 | nginx + halaman `vm101` | Backend berbobot 1 |
| vm102 | 192.168.56.22 | nginx + halaman `vm102` | Backend berbobot 2 |
| vm201 | 192.168.56.31 | nginx + halaman `vm201` | Backend berbobot 1 |
| vm202 | 192.168.56.32 | nginx + halaman `vm202` | Backend berbobot 2 |
| vm210 | 192.168.56.10 | Python + aiohttp + OpenRC | LB Sufferage pada port 80 |

Hostname guest VM 210 adalah `vm-lb`; nomor VM pada Proxmox tetap 210.
Nama tampilan VM 102 pada Proxmox dapat berupa `Copy-of-VM-vm101`, sementara
halaman dan hostname guest mengidentifikasinya sebagai vm102.

## Apa yang ada di host pve1/pve2?

Keduanya menjalankan hypervisor Proxmox, bridge jaringan, disk VM, dan manajemen
cluster. Tidak ada script Sufferage atau Locust yang dipasang pada host Proxmox.
Repo ini tidak mengubah atau membuat ulang cluster, bridge, IP, maupun disk VM.
Konfigurasi guest tersedia sebagai ringkasan di atas; image VM tidak disertakan.

## Apa yang ada pada backend?

Keempat backend menjalankan Alpine Linux dan nginx. File relevannya sama:

```text
/etc/nginx/nginx.conf
/etc/nginx/mime.types
/etc/nginx/http.d/default.conf
/var/www/localhost/htdocs/index.html
```

Salinan aktual dipisahkan pada `backends/vm101/`, `vm102/`, `vm201/`, dan `vm202/`,
dengan struktur direktori mengikuti lokasi asal. Semua dibaca melalui SSH;
tidak ada perubahan konfigurasi nginx saat pengambilan salinan.

Tidak ada program Python pemroses pekerjaan pada backend. Nginx melayani halaman
root yang kecil, dengan isi nama VM. File indeks masing-masing mengembalikan
`vm101`, `vm102`, `vm201`, atau `vm202`.

## Apa yang ada pada vm210?

| Lokasi vm210 | Sumber di repo | Isi |
|---|---|---|
| `/opt/sufferage-lb/lb.py` | `vm210/lb.py` | HTTP proxy, antrean, scheduler, health check, CSV |
| `/etc/init.d/sufferage-lb` | `vm210/openrc/sufferage-lb` | Layanan OpenRC autostart |
| `/usr/local/sbin/run-sufferage-lb` | `vm210/openrc/run-sufferage-lb` | Membuka proses Sufferage dengan CSV baru |
| `/var/log/sufferage-lb/run-*/requests.csv` | Dihasilkan saat berjalan | Log request dari sisi LB |

Nginx tidak memakai port 80 di vm210. Port tersebut dipakai Python LB.
Autostart ini berjalan ketika vm210 boot; menyalakan node/guest melalui VirtualBox
dan Proxmox tetap langkah yang terpisah.

## Alur request

1. Locust di Windows meminta `http://192.168.56.10/`.
2. LB memasukkan request ke antrean dan membuat mini-batch.
3. Sufferage memilih backend sehat berdasarkan prediksi completion time.
4. LB meneruskan HTTP ke nginx backend.
5. Respons nginx dikirim kembali ke Windows melalui LB.
6. LB menambahkan `X-LB-Backend` dan `X-LB-Algorithm`.
7. Locust dan LB menyimpan request ID yang sama pada log masing-masing.

Sufferage membagi **request HTTP**, bukan memindahkan VM atau membagi vCPU host.
