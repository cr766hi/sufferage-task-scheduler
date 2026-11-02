# Koleksi Grafik & Diagram Mermaid untuk Laporan Sufferage
Dokumen ini berisi kode Mermaid siap pakai berdasarkan data pengujian **240 Task (`batch-20261031T123432Z-28cd6a`)** yang tercantum dalam laporan Word (`Laporan_Task_Scheduler_Sufferage.docx`).

Anda dapat membuka file ini di Markdown Preview (VS Code / Obsidian / GitHub) atau menyalin kodenya ke [Mermaid Live Editor](https://mermaid.live), lalu screenshot hasilnya untuk dimasukkan ke dalam file `.docx`.

---

## 1. Diagram Arsitektur Infrastruktur & Alur Sistem
Menampilkan topologi dari Windows, 2 Node Proxmox, 4 Worker heterogen, dan 1 Scheduler.

```mermaid
flowchart TD
    subgraph Windows ["Client Host: Laptop Windows (192.168.56.1)"]
        Dataset["Dataset Input (demo240.csv)<br/>240 Task Batch"]
        Report["Laporan & HTML Dashboard<br/>(hasil_pengujian.html)"]
    end

    subgraph PVE2 ["Proxmox Node 2 (pve2: 192.168.56.12)"]
        subgraph VM210 ["vm210 (1 vCPU, 1 GB RAM) - 192.168.56.10"]
            Scheduler["Master Task Scheduler<br/>(Algoritma Sufferage)"]
        end
        VM201["vm201 Worker (1 vCPU)<br/>56 Task | 364 Unit Kerja"]
        VM202["vm202 Worker (2 vCPU)<br/>50 Task | 810 Unit Kerja"]
    end

    subgraph PVE1 ["Proxmox Node 1 (pve1: 192.168.56.11)"]
        VM101["vm101 Worker (1 vCPU)<br/>73 Task | 254 Unit Kerja"]
        VM102["vm102 Worker (2 vCPU)<br/>61 Task | 540 Unit Kerja"]
    end

    Dataset -->|1. Submit Batch| Scheduler
    Scheduler -->|2. HTTP RPC| VM101
    Scheduler -->|2. HTTP RPC| VM102
    Scheduler -->|2. HTTP RPC| VM201
    Scheduler -->|2. HTTP RPC| VM202
    VM101 -->|3. Respon & Checksum| Scheduler
    VM102 -->|3. Respon & Checksum| Scheduler
    VM201 -->|3. Respon & Checksum| Scheduler
    VM202 -->|3. Respon & Checksum| Scheduler
    Scheduler -->|4. Simpan CSV & Metrik| Report
```

---

## 2. Diagram Logika Alur Algoritma Sufferage
Menjelaskan step-by-step bagaimana algoritma mengambil keputusan di VM210.

```mermaid
flowchart TD
    Start(["Mulai: Batch Diterima (Arrival = 0)"]) --> Init["Inisialisasi Ready Time setiap Worker = 0"]
    Init --> Check{"Apakah masih ada<br/>task tersisa?"}
    
    Check -- Ya --> Group["Kelompokkan Task berdasarkan Jenis<br/>(Light, Medium, Heavy)"]
    Group --> CalcCT["Hitung Completion Time (CT) untuk Tiap Worker:<br/>CT = Ready Time + ETC"]
    CalcCT --> FindBest["Tentukan:<br/>- Best Worker (CT Terkecil)<br/>- Second Best Worker (CT Terkecil Kedua)"]
    FindBest --> CalcSuff["Hitung Nilai Sufferage:<br/>Sufferage = Second CT - Best CT"]
    CalcSuff --> SelectMax["Pilih Task dengan Sufferage Terbesar<br/>(Paling menderita jika tidak dapat worker terbaik)"]
    SelectMax --> Assign["Alokasikan Task ke Best Worker"]
    Assign --> UpdateReady["Perbarui Ready Time Worker:<br/>Ready Time = Best CT"]
    UpdateReady --> Check

    Check -- Tidak --> Execute["Jalankan Antrean secara Paralel pada 4 Worker"]
    Execute --> End(["Selesai (Semua Task Sukses)"])
```

---

## 3. Komposisi Dataset Pengujian (Pie Chart)
Menampilkan proporsi 240 task: 120 ringan, 72 sedang, 48 berat.

```mermaid
pie title Komposisi Dataset Pengujian (Total: 240 Task)
    "Ringan / Light (2 Unit)" : 120
    "Sedang / Medium (8 Unit)" : 72
    "Berat / Heavy (24 Unit)" : 48
```

---

## 4. Distribusi Beban Komputasi / Unit Kerja per Worker (Pie Chart)
Menampilkan persentase pembagian total 1.968 unit kerja PBKDF2-SHA256 pada keempat worker.

```mermaid
pie title Distribusi Beban Komputasi (Total: 1.968 Unit Kerja)
    "vm101 (1 vCPU) - 254 Unit (12.9%)" : 254
    "vm102 (2 vCPU) - 540 Unit (27.4%)" : 540
    "vm201 (1 vCPU) - 364 Unit (18.5%)" : 364
    "vm202 (2 vCPU) - 810 Unit (41.2%)" : 810
```

---

## 5. Total Alokasi Unit Kerja per Worker (Bar Chart)
Memperlihatkan bahwa VM dengan 2 vCPU (`vm102` & `vm202`) memikul 68,6% beban kerja.

```mermaid
xychart-beta
    title "Total Unit Kerja yang Dikerjakan per Worker"
    x-axis ["vm101 (1 vCPU)", "vm102 (2 vCPU)", "vm201 (1 vCPU)", "vm202 (2 vCPU)"]
    y-axis "Unit Komputasi (Iterasi PBKDF2)" 0 --> 900
    bar [254, 540, 364, 810]
```

---

## 6. Jumlah Task yang Dialokasikan per Worker (Bar Chart)
Perbandingan jumlah task logis yang masuk ke masing-masing worker.

```mermaid
xychart-beta
    title "Jumlah Task yang Dialokasikan per Worker"
    x-axis ["vm101 (1 vCPU)", "vm102 (2 vCPU)", "vm201 (1 vCPU)", "vm202 (2 vCPU)"]
    y-axis "Jumlah Task" 0 --> 80
    bar [73, 61, 56, 50]
```

---

## 7. Rata-Rata Waktu Tunggu (Waiting Time) per Jenis Task (Bar Chart)
Bukti kuat cara kerja Sufferage: Task berat didahulukan sehingga waiting time-nya paling singkat!

```mermaid
xychart-beta
    title "Rata-rata Waktu Tunggu (Waiting Time) per Jenis Task"
    x-axis ["Ringan (Light)", "Sedang (Medium)", "Berat (Heavy)"]
    y-axis "Waktu Tunggu (Detik)" 0 --> 25
    bar [20.43, 13.88, 9.77]
```

---

## 8. Rata-Rata Turnaround Time per Jenis Task (Bar Chart)
Turnaround time dihitung dari batch diterima ($t=0$) sampai task selesai ($Waiting + Execution$).

```mermaid
xychart-beta
    title "Rata-rata Turnaround Time per Jenis Task"
    x-axis ["Ringan (Light)", "Sedang (Medium)", "Berat (Heavy)"]
    y-axis "Turnaround Time (Detik)" 0 --> 25
    bar [20.81, 14.38, 10.40]
```

---

## 9. Perbandingan Prediksi Antrean vs Eksekusi Aktual vs Makespan (Bar Chart)
Evaluasi estimasi penjadwalan terhadap realitas sistem.

```mermaid
xychart-beta
    title "Perbandingan Estimasi Durasi dan Waktu Nyata Batch"
    x-axis ["Prediksi Antrean Virtual", "Fase Eksekusi Aktual", "Total Makespan Batch"]
    y-axis "Durasi (Detik)" 0 --> 35
    bar [22.54, 30.00, 31.24]
```

---

## 10. Utilisasi CPU Rata-Rata dan Puncak per Mesin (Bar Chart)
Penggunaan CPU guest dinormalisasi terhadap seluruh core yang dimiliki tiap VM.

```mermaid
xychart-beta
    title "Utilisasi CPU Rata-Rata per VM (%)"
    x-axis ["vm101 (1 vCPU)", "vm102 (2 vCPU)", "vm201 (1 vCPU)", "vm202 (2 vCPU)", "vm210 (Scheduler)"]
    y-axis "CPU (%)" 0 --> 100
    bar [39.07, 25.45, 28.27, 16.77, 77.07]
```

```mermaid
xychart-beta
    title "Utilisasi CPU Puncak (Peak) per VM (%)"
    x-axis ["vm101 (1 vCPU)", "vm102 (2 vCPU)", "vm201 (1 vCPU)", "vm202 (2 vCPU)", "vm210 (Scheduler)"]
    y-axis "CPU Puncak (%)" 0 --> 100
    bar [43.75, 34.01, 36.31, 27.61, 94.48]
```

---

## 11. Utilisasi RAM Rata-Rata per Mesin (Bar Chart)
Penggunaan memori guest relatif stabil pada kisaran 19% - 23% (sangat hemat memori).

```mermaid
xychart-beta
    title "Utilisasi RAM Rata-Rata per VM (%)"
    x-axis ["vm101", "vm102", "vm201", "vm202", "vm210"]
    y-axis "RAM (%)" 0 --> 30
    bar [19.21, 22.41, 19.15, 22.53, 19.46]
```

---

## 12. Estimasi Durasi Task Berat (Heavy) pada Matriks ETC (Bar Chart)
Memperlihatkan keunggulan VM 2 vCPU (`vm202` dan `vm102`) yang memproses task berat jauh lebih cepat dibanding VM 1 vCPU.

```mermaid
xychart-beta
    title "Matriks ETC: Estimasi Durasi Task Berat / Heavy (ms)"
    x-axis ["vm101 (1 vCPU)", "vm102 (2 vCPU)", "vm201 (1 vCPU)", "vm202 (2 vCPU)"]
    y-axis "Durasi (Milidetik)" 0 --> 1000
    bar [849.89, 630.67, 860.43, 496.99]
```

---

## 13. Timeline Eksekusi Antrean Worker (Gantt Chart)
Menampilkan fase eksekusi paralel pada keempat antrean worker hingga makespan tercapai di detik ke-31,24.

```mermaid
gantt
    title Timeline Eksekusi Batch 240 Task pada 4 Worker
    dateFormat X
    axisFormat %s s
    section Persiapan
    Planning Sufferage (0.67 s)       :done, 0, 1
    section Worker pve1
    vm101 (1 vCPU, 73 Task)           :active, 1, 30
    vm102 (2 vCPU, 61 Task)           :active, 1, 30
    section Worker pve2
    vm201 (1 vCPU, 56 Task)           :active, 1, 28
    vm202 (2 vCPU, 50 Task)           :active, 1, 28
    section Status Akhir
    Semua Task Selesai (31.24 s)      :crit, 30, 31
```

