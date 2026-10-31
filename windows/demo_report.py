"""One numbered CSV per Locust test, with requests and final summaries."""
import csv
from datetime import datetime, timezone
import math
from pathlib import Path
import statistics
import time

BACKENDS = ('vm101', 'vm102', 'vm201', 'vm202')
FIELDS = [
    'record_type', 'pengujian', 'timestamp_utc', 'scenario', 'algorithm',
    'target_url', 'nominal_duration_seconds', 'actual_duration_seconds',
    'users_base', 'users_spike', 'pacing_seconds', 'seed', 'active_users',
    'elapsed_seconds', 'method', 'endpoint', 'request_id', 'backend',
    'response_time_ms', 'response_bytes', 'status', 'success', 'error',
    'total_requests', 'successful_requests', 'failed_requests',
    'avg_response_time_ms', 'p95_response_time_ms', 'throughput_rps',
    'error_rate_percent', 'vm101_requests', 'vm102_requests',
    'vm201_requests', 'vm202_requests', 'unassigned_requests',
    'load_imbalance_stddev', 'initial_health_json',
]


class SingleCsvReport:
    def __init__(self, directory, scenario, duration, seed, algorithm, health, target):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        numbers = []
        for path in directory.glob('pengujian *.csv'):
            try:
                numbers.append(int(path.stem.split(' ')[1]))
            except (ValueError, IndexError):
                pass
        number = max(numbers, default=0) + 1
        while True:
            self.path = directory / f'pengujian {number}.csv'
            try:
                self.handle = self.path.open('x', newline='', encoding='utf-8-sig')
                break
            except FileExistsError:
                number += 1
        self.writer = csv.DictWriter(self.handle, fieldnames=FIELDS)
        self.writer.writeheader()
        self.base = dict(pengujian=f'pengujian {number}', scenario=scenario,
                         algorithm=algorithm, target_url=target,
                         nominal_duration_seconds=duration, users_base=10,
                         users_spike=40 if scenario == 'spike' else 10,
                         pacing_seconds=1, seed=seed)
        self.started = time.perf_counter()
        self.rows = []
        self.write('config', initial_health_json=health)

    def write(self, record_type, **values):
        if self.handle is None:
            return
        self.writer.writerow({**self.base, 'record_type': record_type,
                              'timestamp_utc': datetime.now(timezone.utc).isoformat(),
                              **values})
        self.handle.flush()

    def request(self, method, endpoint, request_id, backend, algorithm, response_time,
                response_bytes, status, error, active_users):
        if self.handle is None:
            return
        success = not error and 200 <= status < 400
        self.rows.append((backend, response_time, success))
        self.write('request', method=method, endpoint=endpoint, request_id=request_id,
                   backend=backend, algorithm=algorithm or self.base['algorithm'],
                   response_time_ms=response_time, response_bytes=response_bytes,
                   status=status, success=success, error=error, active_users=active_users,
                   elapsed_seconds=round(time.perf_counter() - self.started, 6))

    @staticmethod
    def metrics(rows, duration):
        times = sorted(row[1] for row in rows)
        total = len(rows)
        successes = sum(row[2] for row in rows)
        return dict(total_requests=total, successful_requests=successes,
                    failed_requests=total - successes,
                    avg_response_time_ms=statistics.mean(times) if times else '',
                    p95_response_time_ms=times[math.ceil(.95 * total) - 1] if times else '',
                    throughput_rps=total / duration if duration > 0 else 0,
                    error_rate_percent=100 * (total - successes) / total if total else 0)

    def finish(self):
        if self.handle is None:
            return
        duration = time.perf_counter() - self.started
        counts = {backend: sum(row[0] == backend for row in self.rows) for backend in BACKENDS}
        self.write('summary', actual_duration_seconds=duration,
                   **self.metrics(self.rows, duration),
                   **{backend + '_requests': count for backend, count in counts.items()},
                   unassigned_requests=sum(row[0] not in BACKENDS for row in self.rows),
                   load_imbalance_stddev=statistics.pstdev(counts.values()))
        for backend in BACKENDS:
            rows = [row for row in self.rows if row[0] == backend]
            self.write('backend_summary', backend=backend, actual_duration_seconds=duration,
                       **self.metrics(rows, duration))
        self.handle.close()
        self.handle = None
        print(f'Hasil lengkap tersimpan: {self.path}', flush=True)
