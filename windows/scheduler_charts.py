"""Offline SVG charts for saved scheduler results; no browser dependencies."""
from html import escape
import math
import statistics

COLORS = ['#2776b8', '#d38a20', '#ad5275', '#2b907a', '#785ab3']
KINDS = [('light', 'Ringan'), ('medium', 'Sedang'), ('heavy', 'Berat')]


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def label(value):
    return f'{value:,.2f}'.rstrip('0').rstrip('.')


def legend(names):
    return '<div class="chart-legend">' + ''.join(
        f'<span><i style="background:{COLORS[i % len(COLORS)]}"></i>{escape(name)}</span>'
        for i, name in enumerate(names)) + '</div>'


def bars(title, note, categories, series, unit, limit=None, stacked=False):
    """Horizontal bars with a shared zero baseline, exact values and SVG titles."""
    parsed = [(name, [number(v) for v in values]) for name, values in series]
    available = [v for _, values in parsed for v in values if v is not None]
    if not available:
        return card(title, note, '<p class="empty-chart">Belum ada data valid.</p>')
    maximum = limit or max(available + [1])
    if stacked:
        maximum = max([sum(values[i] or 0 for _, values in parsed) for i in range(len(categories))] + [1])
    row_height = 46 if stacked else max(54, 26 * len(series) + 16)
    height = 46 + row_height * len(categories)
    left, plot_width = 135, 435
    svg = [f'<svg viewBox="0 0 650 {height}" role="img" aria-label="{escape(title, quote=True)}">']
    for tick in range(5):
        x = left + plot_width * tick / 4
        svg.append(f'<line x1="{x}" x2="{x}" y1="25" y2="{height-8}" stroke="#e1e8f0"/>')
        svg.append(f'<text x="{x}" y="16" text-anchor="middle" class="axis">{label(maximum*tick/4)}</text>')
    for i, category in enumerate(categories):
        top = 31 + i * row_height
        svg.append(f'<text x="125" y="{top+15}" text-anchor="end" class="axis">{escape(str(category))}</text>')
        offset = 0
        for j, (name, values) in enumerate(parsed):
            value = values[i]
            y = top if stacked else top + j * 26
            if value is None:
                if not stacked:
                    svg.append(f'<text x="{left+5}" y="{y+15}" class="axis">tidak tersedia</text>')
                continue
            width = plot_width * max(value, 0) / maximum
            x = left + offset
            hint = escape(f'{category} · {name}: {label(value)} {unit}')
            svg.append(f'<rect x="{x:.2f}" y="{y}" width="{width:.2f}" height="19" rx="3" fill="{COLORS[j%len(COLORS)]}"><title>{hint}</title></rect>')
            if stacked:
                if width > 30:
                    svg.append(f'<text x="{x+width/2:.2f}" y="{y+14}" text-anchor="middle" fill="white" font-size="11">{label(value)}</text>')
                offset += width
            else:
                svg.append(f'<text x="{x+width+6:.2f}" y="{y+14}" class="bar-value">{label(value)}</text>')
        if stacked:
            total = sum(values[i] or 0 for _, values in parsed)
            svg.append(f'<text x="{left+offset+6:.2f}" y="{top+14}" class="bar-value">{label(total)}</text>')
    svg.append('</svg>')
    return card(title, note, legend([s[0] for s in series]) + f'<div class="chart-unit">Sumbu angka: {escape(unit)}</div>' + ''.join(svg))


def card(title, note, body):
    return '<article class="chart-card"><h3>'+escape(title)+'</h3><p>'+escape(note)+'</p>'+body+'</article>'


def resource_line(rows):
    samples = [r for r in rows if r['record_type'] == 'resource_sample']
    vms = sorted({r['vm'] for r in samples})
    end = max([number(r.get('elapsed_ms')) or 0 for r in samples] + [1]) / 1000
    elements = ['<svg viewBox="0 0 650 280" role="img" aria-label="CPU sepanjang eksekusi">']
    for pct in (0, 25, 50, 75, 100):
        y = 225 - pct * 1.9
        elements.append(f'<line x1="45" x2="620" y1="{y}" y2="{y}" stroke="#e1e8f0"/><text x="37" y="{y+4}" text-anchor="end" class="axis">{pct}%</text>')
    for tick in range(5):
        x = 45 + 575*tick/4
        elements.append(f'<text x="{x}" y="247" text-anchor="middle" class="axis">{label(end*tick/4)}</text>')
    elements.append('<text x="330" y="272" text-anchor="middle" class="axis">Waktu sejak batch diterima (detik)</text>')
    count = 0
    for i, vm in enumerate(vms):
        points = []
        def flush():
            if len(points) > 1:
                elements.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{COLORS[i%len(COLORS)]}" stroke-width="2"/>')
            points.clear()
        for r in sorted([r for r in samples if r['vm'] == vm], key=lambda r: number(r.get('elapsed_ms')) or 0):
            value, elapsed = number(r.get('cpu_percent')), number(r.get('elapsed_ms'))
            if r.get('resource_status') != 'ok' or value is None or elapsed is None:
                flush()
                continue
            x, y = 45 + 575*(elapsed/1000)/end, 225 - value*1.9
            points.append(f'{x:.2f},{y:.2f}')
            hint = escape(f'{vm} · {label(elapsed/1000)} s · CPU {label(value)}%')
            elements.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="{COLORS[i%len(COLORS)]}"><title>{hint}</title></circle>')
            count += 1
        flush()
    elements.append('</svg>')
    body = legend(vms) + ''.join(elements) if count else '<p>Belum ada sampel CPU valid.</p>'
    return card('CPU sepanjang eksekusi', 'Titik adalah sampel aktual; garis membantu mengikuti perubahan. Sampel gagal memutus garis, bukan dianggap 0%.', body)


def sufferage_line(tasks):
    data = sorted([(number(t.get('allocation_order')), number(t.get('sufferage_ms')), t.get('task_id', ''))
                   for t in tasks if number(t.get('allocation_order')) is not None and number(t.get('sufferage_ms')) is not None])
    title = 'Sufferage sepanjang urutan alokasi'
    note = 'Nilai task yang dipilih pada setiap langkah, dalam ms. Nilai dapat naik/turun karena CT dihitung ulang setelah reservasi worker.'
    if not data:
        return card(title, note, '<p>Belum ada jejak alokasi valid.</p>')
    maximum, last = max([d[1] for d in data] + [1]), max([d[0] for d in data] + [1])
    svg = ['<svg viewBox="0 0 650 280" role="img" aria-label="Sufferage per urutan alokasi">']
    for tick in range(5):
        y = 225 - 190*tick/4
        x = 65 + 555*tick/4
        svg.append(f'<line x1="65" x2="620" y1="{y}" y2="{y}" stroke="#e1e8f0"/><text x="57" y="{y+4}" text-anchor="end" class="axis">{label(maximum*tick/4)}</text>')
        svg.append(f'<text x="{x}" y="247" text-anchor="middle" class="axis">{label(last*tick/4)}</text>')
    points = [(65+555*order/last, 225-190*value/maximum) for order,value,_ in data]
    svg.append('<polyline points="'+' '.join(f'{x:.2f},{y:.2f}' for x,y in points)+'" fill="none" stroke="#2776b8" stroke-width="1.5"/>')
    for (order,value,task), (x,y) in zip(data, points):
        hint = escape(f'Urutan {label(order)} · {task} · Sufferage {label(value)} ms')
        svg.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.5" fill="#2776b8"><title>{hint}</title></circle>')
    svg.append('<text x="330" y="272" text-anchor="middle" class="axis">Urutan keputusan alokasi</text></svg>')
    return card(title,note, '<div class="chart-unit">Sumbu vertikal: Sufferage (ms)</div>'+''.join(svg))


def batch_charts(rows, summary):
    tasks = [r for r in rows if r['record_type'] == 'task']
    done = [r for r in tasks if r.get('status') == 'completed']
    workers = sorted([r for r in rows if r['record_type'] == 'worker_summary'], key=lambda r: r['worker'])
    names = [r['worker'] + ' · ' + r.get('capacity', '?') + ' vCPU' for r in workers]
    resources = sorted([r for r in rows if r['record_type'] == 'resource_summary'], key=lambda r: r['vm'])
    seconds = lambda value: number(value)/1000 if number(value) is not None else None
    mean = lambda values: statistics.mean(values) if values else None
    charts = []
    charts.append(bars('Komposisi dataset', 'Jumlah input per jenis; rasio unit kerja ringan : sedang : berat = 1 : 4 : 12.',
        [name for _, name in KINDS], [('Task', [sum(t['task_type'] == kind for t in tasks) for kind, _ in KINDS])], 'task'))
    charts.append(bars('Status eksekusi', 'Task gagal dan dilewati ditampilkan terpisah agar masalah tetap terlihat.',
        ['Selesai', 'Gagal', 'Dilewati'], [('Task', [sum(t.get('status') == state for t in tasks) for state in ('completed','failed','skipped')])], 'task'))
    charts.append(bars('Jenis task pada setiap worker', 'Satu batang adalah jumlah task pada satu VM, dibagi menurut jenisnya.', names,
        [(name, [sum(t['worker'] == w['worker'] and t['task_type'] == kind for t in tasks) for w in workers]) for kind, name in KINDS], 'task', stacked=True))
    charts.append(bars('Beban kerja pada setiap worker', 'Unit kerja menjumlahkan bobot task. Task lebih sedikit bisa membawa beban lebih besar.', names,
        [('Unit kerja', [sum(number(t.get('units')) or 0 for t in tasks if t['worker'] == w['worker']) for w in workers])], 'unit kerja'))
    charts.append(bars('Waiting dan turnaround per jenis', 'Hanya task sukses. Semua arrival = 0; turnaround mencakup waktu tunggu dan eksekusi.',
        [name for _, name in KINDS], [(name, [mean([seconds(t[key]) for t in done if t['task_type'] == kind and number(t.get(key)) is not None]) for kind, _ in KINDS]) for name, key in [('Waiting','waiting_ms'),('Turnaround','turnaround_ms')]], 'detik'))
    charts.append(bars('Waktu selesai tiap worker', 'Waktu relatif terhadap penerimaan batch. Bandingkan posisi ujung batang untuk melihat selisih selesai.', names,
        [('Terakhir selesai', [max([seconds(t['finish_ms']) for t in done if t['worker'] == w['worker']] or [None]) for w in workers])], 'detik'))
    charts.append(bars('ETC versus eksekusi aktual', 'Rata-rata per task sukses yang dialokasikan, dipisah menurut jenis. Durasi aktual mencakup RPC.',
        [name for _, name in KINDS], [(name, [mean([number(t[key]) for t in done if t['task_type'] == kind and number(t.get(key)) is not None]) for kind, _ in KINDS]) for name, key in [('ETC','etc_ms'),('Aktual','execution_ms')]], 'ms'))
    charts.append(bars('Prediksi dan durasi aktual batch', 'Prediksi antrean dibanding fase eksekusi; makespan total juga mencakup planning/persiapan. Kalibrasi di luar batch.',
        ['Prediksi antrean','Eksekusi aktual','Makespan total'], [('Durasi', [summary.get(key) for key in ('predicted_makespan_seconds','execution_phase_seconds','makespan_seconds')])], 'detik'))
    for resource, title in [('cpu','CPU'),('ram','RAM')]:
        charts.append(bars(title + ' tiap VM', 'Rata-rata dan puncak teramati. CPU dinormalisasi terhadap seluruh vCPU; RAM terhadap memori guest.',
            [r['vm'] for r in resources], [(name,[r.get(resource+'_'+key+'_percent') for r in resources]) for name,key in [('Rata-rata','avg'),('Puncak','peak')]], '%', limit=100))
    charts.append(resource_line(rows))
    charts.append(sufferage_line(tasks))
    return '<div class="chart-grid">'+''.join(charts)+'</div>'


def charts_dashboard(runs):
    if not runs:
        return '<p>Belum ada hasil pengujian. Grafik akan muncul setelah batch selesai dan CSV disimpan.</p>'
    latest = runs[-1][0]
    options, panels = [], []
    for number_, path, summary, rows in runs:
        text = f'Pengujian {number_} · {summary.get("dataset_name", "")} · {summary.get("batch_status", "")}'
        options.append(f'<option value="run-{number_}"'+(' selected' if number_ == latest else '')+'>'+escape(text)+'</option>')
        panels.append(f'<div class="chart-panel" id="run-{number_}"'+(' hidden' if number_ != latest else '')+'><p class="chart-context">'+escape(text)+' · ETC '+escape(summary.get('calibration_id','—'))+'</p>'+batch_charts(rows,summary)+'</div>')
    selector = '<label class="chart-picker">Pilih hasil untuk grafik <select id="chart-run" onchange="document.querySelectorAll(\'.chart-panel\').forEach(p=>p.hidden=p.id!==this.value)">'+''.join(options)+'</select></label>'
    comparison = ''
    if len(runs) > 1:
        categories = [f'Uji {r[0]} · {r[2].get("total_tasks", "?")} task' for r in runs]
        comparison = '<h3 class="comparison-heading">Perbandingan seluruh pengujian</h3><p>Perbandingan yang setara memerlukan dataset, ETC dan kondisi VM yang sama. Status/dataset lengkap tersedia pada tabel detail.</p><div class="chart-grid">'
        for key, title, unit in [('makespan_seconds','Makespan antar-pengujian','detik'),('throughput_tasks_per_second','Throughput antar-pengujian','task/detik')]:
            comparison += bars(title, 'Setiap batang mewakili satu batch; hasil gagal tetap disertakan.', categories, [(title,[r[2].get(key) for r in runs])], unit)
        comparison += '</div>'
    return selector+''.join(panels)+comparison


CHART_CSS = '''
.chart-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;margin-top:20px}
.chart-card{border:1px solid #dce5ef;border-radius:10px;padding:18px;background:#fff;min-width:0}
.chart-card h3{font-size:17px;margin:0;color:#17304b}.chart-card p{font-size:13px;line-height:1.6;min-height:42px}
.chart-card svg{display:block;width:100%;height:auto;overflow:visible}.axis{font:12px 'Segoe UI',Arial;fill:#536780}.bar-value{font:12px 'Segoe UI',Arial;fill:#17304b}
.chart-legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;margin:12px 0}.chart-legend span{display:inline-flex;align-items:center;gap:5px}.chart-legend i{width:10px;height:10px;border-radius:2px;display:inline-block}
.chart-unit{font-size:11px;color:#63788c;margin-bottom:8px}.chart-picker{display:flex;gap:14px;align-items:center;flex-wrap:wrap;font-weight:600}
.chart-picker select{padding:10px 12px;border:1px solid #b9cede;border-radius:6px;background:#f4f8fc;color:#17304b;max-width:100%;font:inherit}
.chart-context{font-size:13px;padding:10px 14px;background:#ecf3fa;border-radius:6px}.comparison-heading{margin-top:28px}
[hidden]{display:none!important}@media(max-width:900px){.chart-grid{grid-template-columns:1fr}}
@media print{.chart-grid{grid-template-columns:1fr 1fr}.chart-card{break-inside:avoid}.chart-picker{display:none}}
'''
