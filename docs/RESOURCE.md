# Resource utilization guest

Scheduler mengambil sampel empat worker melalui `/metrics` port 8080 dan membaca
vm210 secara lokal. Sampling setiap dua detik selama eksekusi batch, di luar
perhitungan task selesai/throughput. Pemantauan tetap memberi sedikit overhead.

- CPU busy = user + nice + system + irq + softirq dari `/proc/stat`.
- CPU total = delapan counter pertama; idle/iowait/steal tidak dianggap busy.
- CPU interval = 100 × delta busy / delta total; guest/guest_nice tidak dijumlah dua kali.
- CPU rata-rata = 100 × jumlah delta busy / jumlah delta total, puncak = interval maksimum.
- CPU 100% berarti seluruh vCPU guest sibuk, bukan satu vCPU saja.
- RAM terpakai = MemTotal − MemAvailable dari `/proc/meminfo`.
- RAM rata-rata berdasarkan sampel valid, puncak berdasarkan snapshot maksimum.

Sampel pertama menyediakan baseline CPU. Setelah reboot/error, baseline direset.
Data hilang dicatat sebagai error dengan nilai kosong, bukan 0%. Tabel menyertakan
jumlah sampel OK/gagal. Batch singkat bisa selesai sebelum interval CPU valid.
Ini resource guest, bukan host Proxmox atau laptop fisik. Definisi procfs mengacu
ke [dokumentasi Linux](https://www.kernel.org/doc/html/latest/filesystems/proc.html).

Resource hanya metrik evaluasi. Input Sufferage adalah ETC terukur dan ready time.
