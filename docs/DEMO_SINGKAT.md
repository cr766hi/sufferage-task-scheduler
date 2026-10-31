# Urutan demo langsung

## 1. Nyalakan VM

Nyalakan pve1 dan pve2 di VirtualBox. Pada Proxmox pastikan VM 101, 102, 201, 202,
dan 210 running. Tunggu 1–2 menit sampai guest siap. LB dan worker autostart.

## 2. Cek LB dari PowerShell Windows

```powershell
cd E:\testsokarealworld
curl.exe --noproxy '*' http://192.168.56.10/__lb/health
curl.exe --noproxy '*' -i http://192.168.56.10/task/heavy
```

Tunjukkan `algorithm: sufferage`, `workload: mixed-cpu-v1`, empat backend sehat,
header backend pilihan dan JSON task CPU. Jika backend belum sehat, periksa VM
yang bersangkutan sebelum tes. Jangan mematikan host Proxmox.

## 3. Buka PowerShell kedua: SSH langsung ke LB

```powershell
ssh root@192.168.56.10
```

Masukkan password login melalui prompt. Setelah berada **di dalam vm210**:

```sh
hostname
rc-service sufferage-lb status
grep -n 'def sufferage_plan' /opt/sufferage-lb/lb.py
wget -qO- http://127.0.0.1/__lb/health | python3 -m json.tool
latest=$(ls -td /var/log/sufferage-lb/run-* | head -n 1)
tail -f "$latest/requests.csv"
```

`hostname` menampilkan `vm-lb`. Service dan lokasi source menunjukkan LB berjalan
di guest tersebut. Biarkan `tail` terbuka; request baru akan terlihat saat tes.
CSV memuat backend, jenis task, waktu respons, estimasi kerja dan nilai Sufferage.

## 4. Kembali ke PowerShell pertama: jalankan Locust

Jika proses Locust versi lama masih terbuka, Ctrl+C dahulu agar kode baru dimuat.

```powershell
cd E:\testsokarealworld
.\windows\demo_locust.ps1 -Scenario stable -Duration 60
```

Buka **http://127.0.0.1:8089/** lalu klik **Start**. Biarkan PowerShell tetap
terbuka. Locust memakai 10 user dan campuran task ringan/sedang/berat 50/30/20.
Tunjukkan baris `task/light`, `task/medium`, `task/heavy`, serta grafik respons.
Beralih ke terminal SSH untuk menunjukkan log nyata sedang bertambah.

## 5. Setelah tes selesai: tunjukkan tabel hasil

Buka `E:\testsokarealworld\hasil_pengujian.html` dengan browser, lalu Refresh.
Tunjukkan secara berurutan:

1. Rata-rata/p95 response time, throughput dan error rate.
2. Perbandingan task ringan/sedang/berat dan VM penerimanya.
3. CPU/RAM rata-rata serta puncak setiap backend dan vm210.
4. Buka **Lihat bukti perhitungan Sufferage**: CT kedua − CT terbaik dan urutan alokasi.

Sumber hasil tetap satu file: `E:\testsokarealworld\results\pengujian N.csv`.
Jangan membandingkan tes halaman nginx lama dengan task CPU baru sebagai bukti
peningkatan algoritma.

Pada terminal SSH, Ctrl+C menghentikan tampilan log saja. Untuk menunjukkan metrik
guest LB secara langsung:

```sh
wget -qO- http://127.0.0.1/__lb/metrics | python3 -m json.tool
```

Endpoint berisi counter CPU mentah dan RAM snapshot. Persen CPU dihitung otomatis
dari dua snapshot oleh collector Windows dan tersedia pada tabel hasil.

## Opsional: demo lonjakan trafik

Ctrl+C proses Locust sebelumnya, lalu pada PowerShell Windows:

```powershell
.\windows\demo_locust.ps1 -Scenario spike -Duration 60
```

Klik Start lagi. Pola user 10 → 40 → 10; variasi task tetap sama. Untuk fault,
ikuti [panduan lengkap](DEMO.md); matikan hanya satu VM backend, bukan host atau LB.
