"""Summarize measured client CSVs; refuses incomplete or missing repetitions."""
import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import statistics
import sys

BACKENDS = ['vm101', 'vm102', 'vm201', 'vm202']
CAPACITIES = [1, 2, 1, 2]


def percentile(values, proportion=.95):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * proportion) - 1)]


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    groups = defaultdict(list)
    per_run = []
    for run in manifest['runs']:
        if run['state'] != 'complete':
            continue
        name = run['name']
        with (directory / (name + '-client.csv')).open(newline='', encoding='utf-8') as handle:
            rows = list(csv.DictReader(handle))
        with (directory / (name + '-lb.csv')).open(newline='', encoding='utf-8') as handle:
            lb_rows = list(csv.DictReader(handle))
        metadata = json.loads((directory / (name + '-client.json')).read_text(encoding='utf-8'))
        if not rows:
            raise RuntimeError('Empty run: ' + name)
        latencies = [float(r['response_time_ms']) for r in rows]
        errors = sum(bool(r['error']) or not 200 <= int(r['status']) < 400 for r in rows)
        counts = Counter(r['backend'] for r in lb_rows)
        counts_all = [counts[b] for b in BACKENDS]
        weighted = [n / capacity for n, capacity in zip(counts_all, CAPACITIES)]
        duration = float(metadata['duration_seconds'])
        entry = {'scenario': run['scenario'], 'algorithm': run['algorithm'], 'repeat': run['repeat'],
                 'requests': len(rows), 'errors': errors, 'duration_seconds': duration,
                 'mean_response_ms': statistics.mean(latencies), 'p95_response_ms': percentile(latencies),
                 'throughput_rps': len(rows) / duration, 'goodput_rps': (len(rows) - errors) / duration,
                 'error_rate_pct': errors * 100 / len(rows),
                 'imbalance_request_stddev': statistics.pstdev(counts_all),
                 'imbalance_per_capacity_stddev': statistics.pstdev(weighted),
                 **{b + '_assigned': counts[b] for b in BACKENDS},
                 'lb_records': len(lb_rows), 'unassigned': counts['none']}
        per_run.append(entry)
        groups[run['scenario'], run['algorithm']].append((entry, latencies))
    summary = []
    for scenario in manifest['scenarios']:
        for mode in ['round_robin', 'least_connections', 'sufferage']:
            entries = groups[scenario, mode]
            if len(entries) != manifest['repeats']:
                raise RuntimeError(f'Incomplete group {scenario}/{mode}: {len(entries)} of {manifest["repeats"]} repetitions')
            values = [x for _, latencies in entries for x in latencies]
            count = sum(e['requests'] for e, _ in entries)
            errors = sum(e['errors'] for e, _ in entries)
            duration = sum(e['duration_seconds'] for e, _ in entries)
            summary.append({'scenario': scenario, 'algorithm': mode, 'repetitions': len(entries),
                'requests': count, 'mean_response_ms': statistics.mean(values),
                'p95_response_ms': percentile(values), 'throughput_rps': count / duration,
                'goodput_rps': (count - errors) / duration, 'error_rate_pct': 100 * errors / count,
                'mean_run_imbalance_request_stddev': statistics.mean(e['imbalance_request_stddev'] for e, _ in entries),
                'mean_run_imbalance_per_capacity_stddev': statistics.mean(e['imbalance_per_capacity_stddev'] for e, _ in entries),
                'between_run_mean_rt_stddev_ms': statistics.pstdev(e['mean_response_ms'] for e, _ in entries)})
    for filename, records in [('per_run.csv', per_run), ('summary.csv', summary)]:
        with (directory / filename).open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    lines = ['# Hasil eksperimen load balancing', '',
             'Semua angka di bawah berasal dari request nyata ke VM, bukan simulasi lokal.', '',
             '| Skenario | Algoritma | Ulang | Mean ms | p95 ms | Throughput req/s | Error % | Imbalance σ request/run |',
             '|---|---|---:|---:|---:|---:|---:|---:|']
    for r in summary:
        lines.append(f'| {r["scenario"]} | {r["algorithm"]} | {r["repetitions"]} | '
                     f'{r["mean_response_ms"]:.2f} | {r["p95_response_ms"]:.2f} | '
                     f'{r["throughput_rps"]:.2f} | {r["error_rate_pct"]:.2f} | '
                     f'{r["mean_run_imbalance_request_stddev"]:.2f} |')
    lines.extend(['', '## Ringkasan temuan', ''])
    for scenario in manifest['scenarios']:
        subset = [r for r in summary if r['scenario'] == scenario]
        lowest = min(subset, key=lambda r: r['mean_response_ms'])
        lines.append(f'- {scenario}: {lowest["algorithm"]} memiliki mean latency terendah pada pengukuran ini '
                     f'({lowest["mean_response_ms"]:.2f} ms).')
    fault = [r for r in summary if r['scenario'] == 'fault']
    if fault:
        lowest = min(fault, key=lambda r: r['error_rate_pct'])
        lines.append(f'- Saat fault, {lowest["algorithm"]} memiliki error rate terendah '
                     f'({lowest["error_rate_pct"]:.2f}%). Seluruh kegagalan request yang tercatat adalah HTTP 502 saat pemadaman backend.')
    lines.extend(['', 'Sufferage memberi lebih banyak request ke backend berbobot 2. '
        'Untuk memperlihatkan pembagian sesuai kapasitas, berikut stddev jumlah request dibagi bobot '
        '(rata-rata per run; semakin kecil semakin merata relatif terhadap bobot):', '',
        '| Skenario | Round Robin | Least Connections | Sufferage |',
        '|---|---:|---:|---:|'])
    for scenario in manifest['scenarios']:
        by_mode = {r['algorithm']: r for r in summary if r['scenario'] == scenario}
        lines.append('| ' + scenario + ' | ' + ' | '.join(
            f'{by_mode[m]["mean_run_imbalance_per_capacity_stddev"]:.2f}'
            for m in ['round_robin', 'least_connections', 'sufferage']) + ' |')
    lines.extend(['', 'Pada beban stabil dan spike, pembagian Sufferage lebih mendekati bobot kapasitas, '
        'sementara latency-nya lebih tinggi. Batching menambahkan waktu tunggu; eksperimen ini '
        'belum memisahkan biaya batching dari biaya penjadwalan. Hasil berlaku untuk halaman nginx '
        'kecil dan seragam dalam emulasi ini.'])
    incident_runs = [run for run in manifest['runs'] if run.get('recovery_note')]
    if incident_runs:
        lines.extend(['', '## Kejadian selama pemulihan', '',
            'vm101 sempat gagal boot setelah jendela pengukuran fault selesai. Konsol menunjukkan '
            '`Kernel panic - not syncing: IO-APIC + timer doesn\'t work!`. VM 101 direset secara manual; '
            'host Proxmox tidak diubah. Tidak ada perubahan parameter kernel selama pengukuran. Bukti konsol disimpan di '
            '`evidence/vm101-kernel-panic.png`.', '',
            'Sesi dilanjutkan setelah backend kembali sehat. Pengukuran yang sudah selesai dipertahankan '
            'hanya setelah seluruh ID request klien cocok dengan CSV LB dan durasi ukur lengkap. '
            'Waktu diagnosis/pemulihan di luar jendela tes tidak dimasukkan dalam throughput.', ''])
        for run in incident_runs:
            lines.append(f'- {run["name"]}: {run["requests"]} request, {run["errors"]} error; '
                         'memerlukan reset manual saat pemulihan pascates.')
        if manifest.get('post_test_recovery'):
            lines.extend(['', 'Setelah seluruh pengukuran selesai, vm101 dipulihkan dengan opsi '
                          '`noapic` untuk satu kali boot melalui menu Alpine. File konfigurasi boot '
                          'tidak diubah. Opsi sementara ini tidak dipakai selama 27 pengukuran.'])
    verification_path = directory / 'verification.json'
    if verification_path.exists():
        warnings = json.loads(verification_path.read_text(encoding='utf-8')).get('post_test_locust_csv_export_warnings', [])
        if warnings:
            lines.extend(['', '## Ekspor statistik Locust', '',
                f'Pada {len(warnings)} run, penulis CSV statistik berkala Locust mencatat '
                '`ValueError: I/O operation on closed file.` setelah tes selesai. '
                'Audit memastikan pesan muncul setelah `Shape test completed`, dan seluruh request '
                'tetap lengkap pada log klien serta LB. Run yang terkait: ' +
                ', '.join('`' + w['run'] + '`' for w in warnings) + '.'])
    lines.extend(['', '## Cara membaca hasil', '',
        '- Latensi diukur Locust dari Windows; mean/p95 mencakup seluruh request selesai, termasuk gagal.',
        '- p95 memakai nearest rank pada gabungan request tiga pengulangan, bukan rata-rata p95.',
        '- Tabel memakai log per-request final. Ekspor *_stats.csv bawaan Locust bersifat periodik dan pada sebagian run belum mencakup request terakhir; selisihnya diaudit di verification.json.',
        '- Throughput adalah total request selesai / total durasi ukur; goodput tersedia di summary.csv.',
        '- Imbalance adalah rata-rata population stddev hitungan penugasan empat backend per run, termasuk nol.',
        '- Hitungan penugasan berasal dari CSV LB; request tanpa backend tidak masuk σ dan dicatat terpisah.',
        '- Bobot kapasitas heterogen membuat pembagian jumlah request sama belum tentu optimal. Metrik σ jumlah/bobot tersedia di CSV.',
        '- Workload berupa halaman nginx kecil dan seragam. Hasil tidak membuktikan kinerja Sufferage untuk pekerjaan CPU heterogen.',
        '- Sufferage membayar waktu mini-batch 75 ms; biaya ini sengaja termasuk dalam latensi.',
        '- Beban closed-loop: 10 user, spike 40 user, pacing 1 detik; ini bukan uji saturasi kapasitas maksimum.',
        '- Fault hanya mematikan vm101 pada pertengahan run. Waktu aktual perintah dan pemulihan ada di manifest.json.',
        '- Arsitektur nested tanpa KVM dan riwayat reset host membatasi generalisasi. Konfigurasi aktual dicatat dalam infrastructure.json.',
        '- Tidak ada perubahan konfigurasi nginx, IP, bridge, hostname, atau topologi cluster oleh runner.',
        '', '## Reproduksi', '',
        'Lihat README.md, run_experiments.py, locustfile.py, dan lb.py di folder induk.',
        'Dokumentasi Locust: https://docs.locust.io/en/stable/configuration.html', ''])
    (directory / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines[:len(summary) + 6]))


if __name__ == '__main__':
    main()
