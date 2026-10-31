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
                summaries = [row for row in csv.DictReader(handle)
                             if row.get('record_type') == 'summary']
        except (OSError, csv.Error) as error:
            pending.append(f'{path.name}: belum dapat dibaca ({error})')
            continue
        if summaries:
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
    performance, distribution = [], []
    for path, row in results:
        label = row.get('pengujian', path.stem).capitalize()
        pattern = '10 → 40 → 10' if row.get('scenario') == 'spike' else '10'
        failure_count = row.get('failed_requests', '')
        try:
            error_class = 'error' if float(failure_count or 0) > 0 else 'good'
        except ValueError:
            error_class = ''
        name_link = f'<td class="name"><a href="{escape(path.relative_to(root).as_posix(), quote=True)}">{escape(label)}</a><small>{escape(row.get("algorithm", ""))}</small></td>'
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
    if not performance:
        performance.append('<tr><td colspan="10" class="empty">Belum ada pengujian selesai. Jalankan Locust lalu tunggu tes berhenti.</td></tr>')
        distribution.append('<tr><td colspan="7" class="empty">Pembagian backend muncul setelah tes selesai.</td></tr>')
    latest = results[-1][1] if results else {}
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
</style></head><body><main><header><div class="eyebrow">Laboratorium HTTP Load Balancing</div><h1>Hasil Pengujian Sufferage</h1><p>Bandingkan performa antar pengujian, lalu lihat pembagian request pada setiap VM.</p><span class="tag">Windows Locust → vm210 → 4 backend nginx</span>
<p class="meta">Diperbarui: UPDATED · Angka ditampilkan dengan titik desimal.</p></header><div class="cards">CARDS</div>
<section><h2>Perbandingan performa</h2><p>Metrik utama setiap tes. Klik nama pengujian untuk membuka CSV sumber.</p><div class="scroll"><table><thead><tr><th>Pengujian</th><th>Skenario</th><th>User virtual</th><th>Request</th><th>Rata-rata ↓<br>ms</th><th>P95 ↓<br>ms</th><th>Throughput<br>req/s</th><th>Error rate ↓</th><th>Gagal ↓</th><th>Durasi<br>detik</th></tr></thead><tbody>PERFORMANCE</tbody></table></div></section>
<section><h2>Pembagian request per backend</h2><p>Kapasitas model vm101 : vm102 : vm201 : vm202 = 1 : 2 : 1 : 2.</p><div class="scroll"><table><thead><tr><th>Pengujian</th><th>vm101 · bobot 1</th><th>vm102 · bobot 2</th><th>vm201 · bobot 1</th><th>vm202 · bobot 2</th><th>Tanpa backend</th><th>Std dev jumlah request</th></tr></thead><tbody>DISTRIBUTION</tbody></table></div>
<p class="meta">Hitungan mencakup sukses dan gagal setelah backend dipilih. Std dev memakai populasi empat VM. Karena kapasitas berbeda, jumlah request yang sama rata belum tentu lebih baik.</p></section>
PENDING<section><h2>Cara membaca metrik evaluasi</h2><div class="notes"><div><strong>Waktu respons: rata-rata &amp; P95</strong><p>Rata-rata merangkum semua request. P95 adalah batas waktu yang mencakup sedikitnya 95% request (nearest rank). Keduanya mencakup request gagal.</p></div><div><strong>Throughput &amp; error rate</strong><p>Throughput = request selesai ÷ durasi aktual, termasuk penyelesaian request terakhir. Error rate = request gagal ÷ total × 100%; mencakup timeout, HTTP gagal, dan validasi respons.</p></div><div><strong>Perbandingan yang adil</strong><p>Bandingkan skenario dan durasi yang sama, minimal tiga pengulangan. Trafik saat ini meminta halaman nginx yang seragam; belum ada task ringan/sedang/berat. Tabel ini tidak membuktikan keunggulan atas algoritma lain.</p></div></div></section>
<footer>Sumber: satu CSV per pengujian di folder results. Halaman diperbarui otomatis saat tes selesai. Jika halaman sudah terbuka, tekan Refresh. Untuk membuat ulang: .venv\\Scripts\\python.exe windows\\lihat_hasil.py</footer>
</main></body></html>'''
    for marker, value in [('UPDATED', escape(updated)), ('CARDS', cards),
                          ('PERFORMANCE', ''.join(performance)),
                          ('DISTRIBUTION', ''.join(distribution)), ('PENDING', pending_html)]:
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
