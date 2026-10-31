# Build one readable HTML comparison from the numbered test CSV files.
import argparse
import csv
from datetime import datetime
from html import escape
from pathlib import Path
import re
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def number(path):
    match = re.fullmatch(r'pengujian (\d+)', path.stem)
    return int(match.group(1)) if match else 0


def read_results(directory):
    results, pending = [], []
    for path in sorted(Path(directory).glob('pengujian *.csv'), key=number):
        if not number(path):
            continue
        try:
            with path.open(encoding='utf-8-sig', newline='') as handle:
                all_rows = list(csv.DictReader(handle))
                summaries = [row for row in all_rows if row.get('record_type') == 'summary']
        except (OSError, csv.Error) as error:
            pending.append(f'{path.name}: belum dapat dibaca ({error})')
            continue
        if summaries:
            summaries[-1]['_tasks'] = [row for row in all_rows if row.get('record_type') == 'task_summary']
            summaries[-1]['_resources'] = [row for row in all_rows if row.get('record_type') == 'resource_summary']
            traces = [row for row in all_rows if row.get('record_type') == 'request'
                      and row.get('task_type') in ('light', 'medium', 'heavy') and row.get('sufferage_ms')]
            summaries[-1]['_trace'] = sorted(traces, key=lambda row: float(row['sufferage_ms']), reverse=True)[:8]
            results.append((path, summaries[-1]))
        else:
            pending.append(f'{path.name}: tes belum selesai atau ringkasan belum tersedia')
    return results, pending


def fmt(value, digits=2):
    try:
        return f'{float(value):,.{digits}f}'
    except (TypeError, ValueError):
        return '—'


def cell(value, cls=''):
    return f'<td class="{cls}">{escape(str(value))}</td>'


def generate_report(root=ROOT):
    root = Path(root)
    results, pending = read_results(root / 'results')
    performance, distribution, task_rows, resource_rows = [], [], [], []
    for path, row in results:
        label = row.get('pengujian', path.stem).capitalize()
        pattern = '10 → 40 → 10' if row.get('scenario') == 'spike' else '10'
        failure_count = row.get('failed_requests', '')
        try:
            error_class = 'error' if float(failure_count or 0) > 0 else 'good'
        except ValueError:
            error_class = ''
        name_link = f'<td class="name"><a href="{escape(path.relative_to(root).as_posix(), quote=True)}">{escape(label)}</a><small>{escape(row.get("algorithm", ""))} · {escape(row.get("workload") or "uniform-nginx-v1")}</small></td>'
        performance.append('<tr>' + name_link
            + cell(row.get('scenario', ''), 'scenario') + cell(pattern)
            + cell(fmt(row.get('total_requests'), 0))
            + cell(fmt(row.get('avg_response_time_ms')))
            + cell(fmt(row.get('p95_response_time_ms')))
            + cell(fmt(row.get('throughput_rps')))
            + cell(fmt(row.get('error_rate_percent')) + '%', error_class)
            + cell(fmt(failure_count, 0))
            + cell(fmt(row.get('actual_duration_seconds'), 1)) + '</tr>')
        counts = [row.get(f'{backend}_requests', '') for backend in ('vm101', 'vm102', 'vm201', 'vm202')]
        distribution.append('<tr>' + cell(label, 'name')
            + ''.join(cell(fmt(count, 0)) for count in counts)
            + cell(fmt(row.get('unassigned_requests'), 0))
            + cell(fmt(row.get('load_imbalance_stddev'))) + '</tr>')
        for resource in row.get('_resources', []):
            vm = resource.get('backend', '')
            resource_rows.append('<tr>' + cell(label, 'name')
                + cell(vm + (' · LB' if vm == 'vm210' else ''), 'scenario')
                + cell(fmt(resource.get('vcpus'), 0))
                + cell(fmt(resource.get('cpu_avg_percent')))
                + cell(fmt(resource.get('cpu_peak_percent')))
                + cell(fmt(resource.get('ram_avg_percent')))
                + cell(fmt(resource.get('ram_peak_percent')))
                + cell(fmt(resource.get('ram_peak_used_mb'), 1) + ' / ' + fmt(resource.get('ram_total_mb'), 1))
                + cell(fmt(resource.get('resource_ok_samples'), 0) + ' / ' + fmt(resource.get('resource_error_samples'), 0))
                + cell(fmt(resource.get('resource_observed_seconds'), 1)) + '</tr>')
        for task in row.get('_tasks', []):
            kind = task.get('task_type', '')
            task_rows.append('<tr>' + cell(label, 'name') + cell(kind, 'scenario')
                + cell(fmt(task.get('total_requests'), 0))
                + cell(fmt(task.get('avg_response_time_ms')))
                + cell(fmt(task.get('p95_response_time_ms')))
                + cell(fmt(task.get('error_rate_percent')) + '%')
                + ''.join(cell(fmt(task.get(backend + '_requests'), 0))
                          for backend in ('vm101', 'vm102', 'vm201', 'vm202')) + '</tr>')
    if not performance:
        performance.append('<tr><td colspan="10" class="empty">Belum ada pengujian selesai. Jalankan Locust lalu tunggu tes berhenti.</td></tr>')
        distribution.append('<tr><td colspan="7" class="empty">Pembagian backend muncul setelah tes selesai.</td></tr>')
    if not resource_rows:
        resource_rows.append('<tr><td colspan="10" class="empty">Belum ada pengujian dengan pemantauan resource. Data lama tidak diisi dengan angka perkiraan.</td></tr>')
    latest = results[-1][1] if results else {}
    if not task_rows:
        task_rows.append('<tr><td colspan="10" class="empty">Belum ada tes mixed-cpu-v1 selesai. Tes lama hanya meminta halaman nginx.</td></tr>')
    trace_rows = []
    for row in latest.get('_trace', []):
        trace_rows.append('<tr>' + cell(row.get('task_type'), 'name')
            + cell(row.get('backend')) + cell(fmt(row.get('estimated_work_ms')))
            + cell(fmt(row.get('best_ct_ms'))) + cell(fmt(row.get('second_ct_ms')))
            + cell(fmt(row.get('sufferage_ms'))) + cell(row.get('batch_id'))
            + cell(row.get('assignment_order')) + '</tr>')
    if not trace_rows:
        trace_rows.append('<tr><td colspan="8" class="empty">Jejak keputusan tersedia setelah tes CPU melalui LB terbaru selesai.</td></tr>')
    updated = datetime.now().astimezone().strftime('%d %b %Y · %H:%M:%S %Z')
    cards = ''.join(f'<div class="card"><span>{escape(label)}</span><strong>{escape(value)}</strong><small>{escape(note)}</small></div>' for label, value, note in [
        ('Pengujian selesai', str(len(results)), 'Semua tes dalam folder results'),
        ('Rata-rata respons', fmt(latest.get('avg_response_time_ms')) + ' ms', 'Pengujian terakhir · lebih rendah lebih baik'),
        ('P95 respons', fmt(latest.get('p95_response_time_ms')) + ' ms', 'Pengujian terakhir · lebih rendah lebih baik'),
        ('Throughput', fmt(latest.get('throughput_rps')) + ' req/s', 'Pengujian terakhir · lihat juga error rate'),
    ])
    pending_html = ('<aside><strong>Belum masuk perbandingan</strong><ul>'
                    + ''.join('<li>' + escape(message) + '</li>' for message in pending)
                    + '</ul></aside>') if pending else ''
    html = '''<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hasil Pengujian Sufferage</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f6fa;color:#15243a;font:15px/1.55 "Segoe UI",Arial,sans-serif}
main{max-width:1460px;margin:auto;padding:40px 32px 64px}.eyebrow{color:#2766a1;font-size:12px;font-weight:700;letter-spacing:2px;text-transform:uppercase}
h1{font-size:34px;line-height:1.2;margin:10px 0}h2{font-size:21px;margin:0 0 4px}p{margin:6px 0;color:#526177}.meta{font-size:12px;margin-top:14px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:28px 0}
.card,section{background:#fff;border:1px solid #dee6f0;border-radius:12px}.card{padding:20px}.card span,.card small{display:block;color:#637188}.card strong{display:block;font-size:28px;line-height:1.4;margin:8px 0}.card small{font-size:11px}
section{padding:24px;margin-top:22px}.scroll{overflow-x:auto;margin-top:20px}table{width:100%;border-collapse:collapse;font-size:13px;white-space:nowrap;font-variant-numeric:tabular-nums}th{text-align:right;background:#edf3f9;color:#40536b;font-size:12px;font-weight:600}th,td{padding:14px 12px;border-bottom:1px solid #e7edf4}td{text-align:right}th:first-child,td.name,td.scenario{text-align:left}.name{font-weight:600}.name small{display:block;font-size:11px;color:#718198;font-weight:400}a{color:#1c609d;text-decoration:none}a:hover{text-decoration:underline}tbody tr:hover{background:#f7fafe}.good{color:#137351;font-weight:700}.error{color:#b62c34;font-weight:700}.empty{text-align:center;padding:36px;color:#637188}.notes{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;margin-top:20px}.notes strong{font-size:13px}.notes p{font-size:12px}aside{background:#fff7df;border:1px solid #ebd99e;padding:16px 24px;border-radius:10px;margin-top:22px}footer{font-size:12px;color:#637188;margin-top:24px}.tag{display:inline-block;background:#e5eef8;color:#215681;border-radius:20px;padding:4px 12px;font-size:12px;margin-top:12px}
@media(max-width:800px){main{padding:24px 16px}.cards{grid-template-columns:repeat(2,1fr)}.notes{grid-template-columns:1fr}section{padding:18px}}@media print{body{background:white}main{padding:0}.card,section{break-inside:avoid}.scroll{overflow:visible}th,td{padding:8px 6px}h1{font-size:26px}}
</style></head><body><main><header><div class="eyebrow">Laboratorium HTTP Load Balancing</div><h1>Hasil Pengujian Sufferage</h1><p>Bandingkan performa antar pengujian, lalu lihat pembagian request pada setiap VM.</p><span class="tag">Windows Locust → vm210 → 4 backend CPU + nginx</span>
<p class="meta">Diperbarui: UPDATED · Angka ditampilkan dengan titik desimal.</p></header><div class="cards">CARDS</div>
<section><h2>Perbandingan performa</h2><p>Metrik utama setiap tes. Klik nama pengujian untuk membuka CSV sumber.</p><div class="scroll"><table><thead><tr><th>Pengujian</th><th>Skenario</th><th>User virtual</th><th>Request</th><th>Rata-rata ↓<br>ms</th><th>P95 ↓<br>ms</th><th>Throughput<br>req/s</th><th>Error rate ↓</th><th>Gagal ↓</th><th>Durasi<br>detik</th></tr></thead><tbody>PERFORMANCE</tbody></table></div></section>
<section><h2>Perbandingan task ringan, sedang, dan berat</h2><p>Kerja CPU nyata: light = 2 unit, medium = 8 unit, heavy = 24 unit. Satu unit = 1.000 iterasi PBKDF2-SHA256. Campuran acak ditargetkan 50% / 30% / 20%.</p><div class="scroll"><table><thead><tr><th>Pengujian</th><th>Task</th><th>Request</th><th>Rata-rata<br>ms</th><th>P95<br>ms</th><th>Error rate</th><th>vm101</th><th>vm102</th><th>vm201</th><th>vm202</th></tr></thead><tbody>TASKROWS</tbody></table></div><p class="meta">Task identik dijalankan pada setiap VM; worker memakai 1 atau 2 proses sesuai vCPU. Rasio 1:4:12 adalah jumlah kerja, bukan jaminan rasio waktu respons. Waktu respons juga mencakup antrean dan jaringan.</p></section>
<section><h2>Pembagian request per backend</h2><p>Kapasitas model vm101 : vm102 : vm201 : vm202 = 1 : 2 : 1 : 2.</p><div class="scroll"><table><thead><tr><th>Pengujian</th><th>vm101 · bobot 1</th><th>vm102 · bobot 2</th><th>vm201 · bobot 1</th><th>vm202 · bobot 2</th><th>Tanpa backend</th><th>Std dev jumlah request</th></tr></thead><tbody>DISTRIBUTION</tbody></table></div>
<p class="meta">Hitungan mencakup sukses dan gagal setelah backend dipilih. Std dev memakai populasi empat VM. Karena kapasitas berbeda, jumlah request yang sama rata belum tentu lebih baik.</p></section>
<section><h2>Resource utilization · CPU dan RAM</h2><p>Resource seluruh guest VM, termasuk layanan OS dan proses worker. Sampel diambil tiap 2 detik; vm210 adalah load balancer.</p><div class="scroll"><table><thead><tr><th>Pengujian</th><th>VM</th><th>vCPU</th><th>CPU rata-rata<br>%</th><th>CPU puncak<br>%</th><th>RAM rata-rata<br>%</th><th>RAM puncak<br>%</th><th>RAM puncak / total<br>MiB</th><th>Sampel<br>OK / gagal</th><th>CPU teramati<br>detik</th></tr></thead><tbody>RESOURCEROWS</tbody></table></div><p class="meta">CPU 100% berarti semua vCPU VM sibuk. CPU rata-rata dihitung dari total selisih busy/total ticks; puncak adalah interval sampel tertinggi. RAM terpakai = MemTotal − MemAvailable; rata-rata RAM adalah rata-rata sampel. Sampel CPU pertama memerlukan baseline sehingga belum punya persen. Tanda — berarti tidak tersedia, bukan 0%. Tes lama tanpa sampel tidak ditampilkan.</p><p class="meta">Ini pengukuran guest, bukan CPU/RAM laptop fisik atau host Proxmox. Pemantauan menambah sedikit beban dan tidak masuk hitungan request/throughput Locust. Metrik ini untuk evaluasi; algoritma Sufferage tetap memakai estimasi kerja dan ready time.</p></section>
<section><details><summary><strong>Lihat bukti perhitungan Sufferage · pengujian terakhir</strong></summary><p>Delapan request dengan nilai Sufferage tertinggi yang terekam. Setiap angka dihitung pada giliran penjadwalan request dalam mini-batch.</p><div class="scroll"><table><thead><tr><th>Task</th><th>Backend terbaik</th><th>Estimasi kerja<br>ms @ kapasitas 1</th><th>CT terbaik<br>ms</th><th>CT kedua<br>ms</th><th>Sufferage<br>ms</th><th>Batch</th><th>Urutan alokasi</th></tr></thead><tbody>TRACEROWS</tbody></table></div><p class="meta">Sufferage = CT kedua − CT terbaik. CT relatif terhadap saat batch dijadwalkan, bukan durasi CPU aktual. Prioritas dihitung ulang setelah setiap alokasi; nilai nol sah ketika dua backend terbaik sama baiknya. Ini jejak pilihan scheduler, bukan seluruh matriks kandidat.</p></details></section>
PENDING<section><h2>Cara membaca metrik evaluasi</h2><div class="notes"><div><strong>Waktu respons: rata-rata &amp; P95</strong><p>Rata-rata merangkum semua request. P95 adalah batas waktu yang mencakup sedikitnya 95% request (nearest rank). Keduanya mencakup request gagal.</p></div><div><strong>Throughput &amp; error rate</strong><p>Throughput = request selesai ÷ durasi aktual, termasuk penyelesaian request terakhir. Error rate = request gagal ÷ total × 100%; mencakup timeout, HTTP gagal, dan validasi respons.</p></div><div><strong>Perbandingan yang adil</strong><p>Bandingkan skenario dan durasi yang sama, minimal tiga pengulangan. Pisahkan workload uniform-nginx-v1 (tes lama) dari mixed-cpu-v1 (task bervariasi). Jangan membandingkan keduanya sebagai peningkatan algoritma. Semua tes demo menggunakan Sufferage; keunggulan atas algoritma lain perlu eksperimen pembanding.</p></div></div></section>
<footer>Sumber: satu CSV per pengujian di folder results. Halaman diperbarui otomatis saat tes selesai. Jika halaman sudah terbuka, tekan Refresh. Untuk membuat ulang: .venv\\Scripts\\python.exe windows\\lihat_hasil.py</footer>
</main></body></html>'''
    for marker, value in [('UPDATED', escape(updated)), ('CARDS', cards),
                          ('PERFORMANCE', ''.join(performance)),
                          ('DISTRIBUTION', ''.join(distribution)), ('TASKROWS', ''.join(task_rows)),
                          ('TRACEROWS', ''.join(trace_rows)), ('RESOURCEROWS', ''.join(resource_rows)),
                          ('PENDING', pending_html)]:
        html = html.replace(marker, value)
    output = root / 'hasil_pengujian.html'
    output.write_text(html, encoding='utf-8')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--open', action='store_true', help='Buka tabel di browser')
    args = parser.parse_args()
    output = generate_report()
    print(f'Tabel hasil: {output}')
    if args.open:
        webbrowser.open(output.as_uri())
