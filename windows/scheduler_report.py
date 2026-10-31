"""One CSV per batch plus one readable comparison page, stdlib only."""
import argparse
import csv
from html import escape
import json
from pathlib import Path
import statistics
import webbrowser


def save_result(root, batch):
    root = Path(root)
    directory = root / 'results'
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob('pengujian *.csv'):
        with path.open(encoding='utf-8-sig', newline='') as handle:
            first = next(csv.DictReader(handle), {})
        if first.get('batch_id') == batch['batch_id']:
            return path
    base = dict(batch_id=batch['batch_id'], algorithm='sufferage', scheduling='offline_batch',
                dataset_name=batch['dataset_name'], dataset_sha256=batch['dataset_sha256'],
                admitted_at_utc=batch['admitted_at_utc'], batch_status=batch['status'])
    rows = [dict(record_type='config', **base)]
    for kind, values in batch['calibration']['etc_ms'].items():
        for worker, value in values.items():
            rows.append(dict(record_type='etc_calibration', task_type=kind, worker=worker,
                etc_ms=value, calibration_id=batch['calibration']['id'],
                calibration_method=batch['calibration']['method']))
    for task in batch['tasks']:
        rows.append(dict(record_type='task', **{key:value for key,value in task.items() if key != 'candidate_ct_ms'},
            **{'ct_' + worker + '_ms': value for worker,value in task['candidate_ct_ms'].items()}))
    rows.append(dict(record_type='batch_summary', **(batch['summary'] or {}), error=batch.get('error','')))
    for worker in batch['workers']:
        assigned = [task for task in batch['tasks'] if task['worker'] == worker['name']]
        done = [task for task in assigned if task['status'] == 'completed']
        rows.append(dict(record_type='worker_summary', worker=worker['name'], capacity=worker['capacity'],
            assigned_tasks=len(assigned), completed_tasks=len(done),
            observed_execution_ms=sum(task['execution_ms'] for task in done)))
    for kind in ('light','medium','heavy'):
        done = [task for task in batch['tasks'] if task['task_type'] == kind and task['status'] == 'completed']
        rows.append(dict(record_type='task_type_summary', task_type=kind, completed_tasks=len(done),
            avg_waiting_ms=statistics.mean(task['waiting_ms'] for task in done) if done else None,
            avg_turnaround_ms=statistics.mean(task['turnaround_ms'] for task in done) if done else None))
    rows += [dict(record_type='resource_sample', **sample) for sample in batch['resources']]
    rows += [dict(record_type='resource_summary', **summary) for summary in batch['resource_summaries']]
    fields = list(dict.fromkeys(['record_type', *base, *(key for row in rows for key in row)]))
    number = 1
    while True:
        path = directory / f'pengujian {number}.csv'
        try:
            handle = path.open('x', encoding='utf-8-sig', newline='')
            break
        except FileExistsError:
            number += 1
    with handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({**base, **row} for row in rows)
    return path


def fmt(value, digits=2):
    try:
        return f'{float(value):,.{digits}f}'
    except (ValueError,TypeError):
        return '—'


def table(headers, rows):
    return '<div class="scroll"><table><thead><tr>' + ''.join('<th>'+escape(header)+'</th>' for header in headers) + '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+escape(str(value))+'</td>' for value in row)+'</tr>' for row in rows) + '</tbody></table></div>'


def generate_report(root):
    root = Path(root)
    runs = []
    for path in (root / 'results').glob('pengujian *.csv'):
        with path.open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.DictReader(handle))
        summary = next((row for row in rows if row.get('record_type') == 'batch_summary'), None)
        if summary:
            runs.append((int(path.stem.split()[-1]), path, summary, rows))
    runs.sort()
    comparison, resources, workers, kinds = [], [], [], []
    for number,path,summary,rows in runs:
        comparison.append([f'Pengujian {number}', summary['dataset_name'], summary['batch_status'],
            summary.get('total_tasks',''), summary.get('completed_tasks',''),
            fmt(summary.get('makespan_seconds')), fmt(summary.get('avg_waiting_ms')),
            fmt(summary.get('avg_turnaround_ms')), fmt(summary.get('throughput_tasks_per_second'))])
        for row in rows:
            if row['record_type'] == 'resource_summary':
                resources.append([f'Pengujian {number}',row['vm'],fmt(row['cpu_avg_percent']),
                    fmt(row['cpu_peak_percent']),fmt(row['ram_avg_percent']),fmt(row['ram_peak_percent']),
                    row['resource_ok_samples']+'/'+row['resource_error_samples'],
                    row['cpu_valid_samples'],fmt(row['resource_observed_seconds'])])
            if row['record_type'] == 'worker_summary':
                workers.append([f'Pengujian {number}',row['worker'],row['capacity'],
                    row['assigned_tasks'],row['completed_tasks'],fmt(row['observed_execution_ms'])])
            if row['record_type'] == 'task_type_summary':
                kinds.append([f'Pengujian {number}',row['task_type'],row['completed_tasks'],
                    fmt(row['avg_waiting_ms']),fmt(row['avg_turnaround_ms'])])
    latest = runs[-1] if runs else None
    trace, execution, etc = [], [], []
    if latest:
        for row in latest[3]:
            if row['record_type'] == 'task':
                trace.append([row['allocation_order'],row['task_id'],row['task_type'],
                    *[fmt(row.get('ct_'+worker+'_ms')) for worker in ('vm101','vm102','vm201','vm202')],
                    fmt(row['sufferage_ms']),row['worker']])
                execution.append([row['task_id'],row['task_type'],row['worker'],row['status'],
                    fmt(row.get('start_ms')),fmt(row.get('finish_ms')),fmt(row.get('waiting_ms')),
                    fmt(row.get('execution_ms')),fmt(row.get('turnaround_ms')),row.get('error','')])
            if row['record_type'] == 'etc_calibration':
                etc.append([row['task_type'],row['worker'],fmt(row['etc_ms'])])
    sections = [
        ('Perbandingan hasil batch', 'Seluruh task datang bersamaan. Metrik utama adalah waktu penyelesaian batch dan waktu tunggu task.',
         table(['Pengujian','Dataset','Status','Task','Selesai','Makespan (s)','Rata-rata tunggu (ms)','Rata-rata turnaround (ms)','Throughput (task/s)'], comparison)),
        ('Ringkasan jenis task', 'Light / medium / heavy benar-benar mengerjakan perhitungan CPU dengan rasio kerja 1:4:12.',
         table(['Pengujian','Jenis','Selesai','Rata-rata tunggu (ms)','Rata-rata turnaround (ms)'], kinds)),
        ('Alokasi ke VM worker', 'Setiap VM menjalankan satu task logis pada satu waktu; task di VM dua vCPU dibagi ke dua proses CPU.',
         table(['Pengujian','Worker','vCPU','Dialokasikan','Selesai','Jumlah durasi eksekusi RPC (ms)'], workers)),
        ('Resource utilization guest', 'CPU/RAM tiap VM, termasuk scheduler vm210. Sampel setiap 2 detik; data hilang tidak dianggap 0%.',
         table(['Pengujian','VM','CPU rata-rata %','CPU puncak %','RAM rata-rata %','RAM puncak %','Sampel OK/gagal','Interval CPU valid','CPU teramati (s)'], resources)),
        ('Jejak Sufferage · batch terakhir', 'CT = ready time worker + ETC task pada worker tersebut. Sufferage = CT terbaik kedua − CT terbaik; ready time diperbarui setelah setiap alokasi.',
         '<details><summary>Lihat seluruh urutan alokasi dan CT kandidat</summary>'+table(['Urutan','Task','Jenis','CT vm101 (ms)','CT vm102 (ms)','CT vm201 (ms)','CT vm202 (ms)','Sufferage (ms)','Worker pilihan'], trace)+'</details>'),
        ('Waktu eksekusi task · batch terakhir', 'Waktu relatif terhadap penerimaan batch pada scheduler. Durasi eksekusi RPC mencakup perjalanan scheduler–worker; CPU time worker terpisah dalam CSV.',
         '<details><summary>Lihat start, finish, waiting, execution, turnaround</summary>'+table(['Task','Jenis','Worker','Status','Start (ms)','Finish (ms)','Waiting (ms)','Execution (ms)','Turnaround (ms)','Error'], execution)+'</details>'),
        ('ETC hasil kalibrasi · batch terakhir', 'Median dua sampel worker_elapsed_ms setelah warmup, dilakukan sebelum batch. Estimasi bukan jaminan waktu aktual.',
         '<details><summary>Lihat matriks estimasi waktu eksekusi</summary>'+table(['Jenis','Worker','ETC (ms)'], etc)+'</details>'),
    ]
    content = ''.join('<section><h2>'+escape(title)+'</h2><p>'+escape(note)+'</p>'+body+'</section>' for title,note,body in sections)
    html = '''<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Task Scheduling Sufferage</title><style>
*{box-sizing:border-box}body{font:15px/1.6 'Segoe UI',Arial,sans-serif;color:#17304b;background:#f2f6fa;margin:0}main{max-width:1460px;padding:36px 28px 64px;margin:auto}h1{font-size:34px;margin:8px 0}h2{font-size:21px;margin:0}p{color:#536780;margin:8px 0 16px}.tag{font-size:12px;color:#2169a6;letter-spacing:2px;text-transform:uppercase;font-weight:700}section{background:white;border:1px solid #dce5ef;border-radius:12px;padding:24px;margin-top:22px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;white-space:nowrap;font-size:13px;font-variant-numeric:tabular-nums}th,td{text-align:right;border-bottom:1px solid #e6edf4;padding:12px}th{background:#ecf3fa;color:#405e7a;font-size:12px}th:first-child,td:first-child{text-align:left}summary{cursor:pointer;color:#246aab;font-weight:600;padding:10px 0}footer{font-size:12px;color:#63788c;margin-top:24px}.notice{border-left:4px solid #2478b7;padding:10px 18px;background:#e6f0fa}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-top:24px}.card{background:white;border:1px solid #dce5ef;padding:20px;border-radius:12px}.card strong{display:block;font-size:25px}.card span{font-size:12px;color:#60778e}@media(max-width:800px){.cards{grid-template-columns:repeat(2,1fr)}main{padding:24px 12px}}
</style></head><body><main><div class="tag">Distributed Task Scheduling</div><h1>Sufferage Task Scheduler</h1><p>Dataset CSV → scheduler vm210 → empat VM worker → hasil penjadwalan.</p><div class="notice">Model: batch statis, task independen, non-preemptive. Transport HTTP hanya untuk kontrol dan eksekusi task. </div>CARDSCONTENT<footer>Waiting = start − arrival. Turnaround = finish − arrival. Makespan = durasi batch sampai seluruh antrean terminal; throughput = task sukses / makespan. Rata-rata waiting/turnaround hanya task sukses. Kalibrasi di luar makespan. Pengukuran guest tidak mewakili host fisik. Hasil pengujian HTTP lama tidak dibandingkan di sini. Refresh halaman setelah batch selesai.</footer></main></body></html>'''
    summary = latest[2] if latest else {}
    cards = '<div class="cards">'+''.join('<div class="card"><span>'+escape(label)+'</span><strong>'+escape(value)+'</strong></div>' for label,value in [
        ('Makespan batch terakhir',fmt(summary.get('makespan_seconds'))+' s'),
        ('Rata-rata waiting',fmt(summary.get('avg_waiting_ms'))+' ms'),
        ('Rata-rata turnaround',fmt(summary.get('avg_turnaround_ms'))+' ms'),
        ('Task selesai',str(summary.get('completed_tasks','—'))+' / '+str(summary.get('total_tasks','—')))])+'</div>'
    output = root / 'hasil_pengujian.html'
    output.write_text(html.replace('CARDS',cards).replace('CONTENT',content), encoding='utf-8')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--open', action='store_true')
    args = parser.parse_args()
    output = generate_report(Path(__file__).resolve().parents[1])
    print(output)
    if args.open:
        webbrowser.open(output.as_uri())
