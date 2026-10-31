"""Submit one dataset batch, watch progress, and save one numbered result CSV."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
from scheduler_report import save_result, generate_report


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', default='http://192.168.56.10')
    parser.add_argument('--dataset', type=Path, default=root / 'datasets/demo40.csv')
    parser.add_argument('--reuse-calibration', action='store_true')
    parser.add_argument('--resume', help='Batch ID, or latest; does not submit again')
    args = parser.parse_args()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def api(path, payload=None, timeout=180):
        request = urllib.request.Request(args.server.rstrip('/') + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Content-Type':'application/json'})
        try:
            with opener.open(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'HTTP {error.code}: {error.read().decode()}') from None
    health = api('/api/health')
    if health.get('role') != 'task_scheduler':
        raise RuntimeError('vm210 is not running the batch task scheduler')
    if args.resume:
        run_id = args.resume
    else:
        with args.dataset.open(encoding='utf-8-sig', newline='') as handle:
            tasks = list(csv.DictReader(handle))
        profiles = json.loads((root / 'workload/task_profiles.json').read_text())
        for task in tasks:
            if int(task['iterations_per_unit']) != profiles['iterations_per_unit']:
                raise ValueError('Dataset iteration count does not match deployed task profile')
        if not args.reuse_calibration or not health['calibrated']:
            print('Mengukur ETC ringan/sedang/berat pada setiap worker (di luar waktu batch)...', flush=True)
            calibration = api('/api/calibrate', {})
            print(json.dumps(calibration['etc_ms'], indent=2), flush=True)
        submitted = api('/api/batches', dict(tasks=tasks, dataset_name=args.dataset.name,
            dataset_sha256=hashlib.sha256(args.dataset.read_bytes()).hexdigest()))
        run_id = submitted['batch_id']
        print('Batch:', run_id, '| task:', len(tasks), flush=True)
    previous = None
    while True:
        progress = api('/api/batches/' + run_id + '?summary=1', timeout=15)
        state = (progress['terminal_tasks'], progress['status'])
        if state != previous:
            print(f"{progress['terminal_tasks']}/{progress['total_tasks']} task | {progress['status']}", flush=True)
            previous = state
        if progress['status'] in ('completed','completed_with_errors','failed'):
            break
        time.sleep(1)
    batch = api('/api/batches/' + run_id, timeout=30)
    path = save_result(root, batch)
    page = generate_report(root)
    print('CSV:', path)
    print('Tabel:', page)
    print(json.dumps(batch.get('summary'), indent=2))
    if batch['status'] != 'completed':
        raise SystemExit('Batch tidak selesai seluruhnya. Periksa status/error tiap task di hasil.')


if __name__ == '__main__':
    main()
