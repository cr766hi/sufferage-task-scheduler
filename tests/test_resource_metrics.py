import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'monitoring'))
sys.path.insert(0, str(ROOT / 'windows'))
from vm_metrics import parse_cpu, parse_memory, snapshot
from resource_monitor import delta
from demo_report import SingleCsvReport


class ResourceMetricsTests(unittest.TestCase):
    def test_cpu_fields_do_not_double_count_guest_and_normalize_by_all_vcpus(self):
        counters = parse_cpu('cpu 100 10 50 800 20 5 5 10 30 40\ncpu0 1 2 3 4\n')
        self.assertEqual(counters['cpu_total_ticks'], 1000)
        self.assertEqual(counters['cpu_busy_ticks'], 170)
        previous = dict(counters, boot_id='boot-a', sample_monotonic_seconds=10)
        current = dict(previous, cpu_total_ticks=1200, cpu_busy_ticks=270, sample_monotonic_seconds=12)
        self.assertEqual(delta(previous, current)['cpu_percent'], 50)
        self.assertEqual(delta(previous, current)['resource_interval_seconds'], 2)
        self.assertEqual(delta(None, current), {})
        self.assertEqual(delta(previous, dict(current, boot_id='boot-b')), {})
        self.assertEqual(delta(previous, dict(current, cpu_total_ticks=900)), {})

    def test_memory_uses_available_and_snapshot_reads_guest_counters(self):
        memory = parse_memory('MemTotal: 1024000 kB\nMemFree: 102400 kB\nMemAvailable: 614400 kB\n')
        self.assertEqual(memory['ram_percent'], 40)
        self.assertEqual(memory['ram_used_mb'], 400)
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            (proc / 'stat').write_text('cpu 1 2 3 4 5 6 7 8\ncpu0 1 2\ncpu1 1 2\n')
            (proc / 'meminfo').write_text('MemTotal: 1024000 kB\nMemAvailable: 614400 kB\n')
            (proc / 'sys/kernel/random').mkdir(parents=True)
            (proc / 'sys/kernel/random/boot_id').write_text('boot-a\n')
            sample = snapshot('vm102', proc)
            self.assertEqual(sample['vcpus'], 2)
            self.assertEqual(sample['vm'], 'vm102')
            self.assertEqual(sample['ram_percent'], 40)
            json.dumps(sample)

    def test_resource_summary_preserves_missing_samples_and_request_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            report = SingleCsvReport(Path(directory) / 'results', 'stable', 60, 1001, 'sufferage', '{}', 'http://localhost')
            for busy, ram in [(20, 20), (40, 40)]:
                report.resource(dict(backend='vm102', resource_status='ok', cpu_percent=busy,
                    cpu_busy_delta_ticks=busy, cpu_total_delta_ticks=100,
                    resource_interval_seconds=2, ram_percent=ram, ram_used_mb=ram * 5,
                    ram_available_mb=500 - ram * 5, ram_total_mb=500, vcpus=2))
            report.resource(dict(backend='vm102', resource_status='error', error='timeout'))
            report.resource(dict(backend='vm101', resource_status='error', error='unreachable'))
            report.request('GET', '/task/heavy', 'id-1', 'vm102', 'sufferage', 50, 10, 200, '', 10, task_type='heavy')
            report.finish()
            with report.path.open(encoding='utf-8-sig', newline='') as handle:
                rows = list(csv.DictReader(handle))
            summary = next(row for row in rows if row['record_type'] == 'summary')
            self.assertEqual(summary['total_requests'], '1')
            resources = {row['backend']: row for row in rows if row['record_type'] == 'resource_summary'}
            self.assertEqual(float(resources['vm102']['cpu_avg_percent']), 30)
            self.assertEqual(float(resources['vm102']['cpu_peak_percent']), 40)
            self.assertEqual(float(resources['vm102']['ram_avg_percent']), 30)
            self.assertEqual(resources['vm102']['resource_ok_samples'], '2')
            self.assertEqual(resources['vm102']['resource_error_samples'], '1')
            self.assertEqual(resources['vm101']['cpu_avg_percent'], '')
            self.assertEqual(resources['vm101']['ram_avg_percent'], '')
            self.assertEqual(len(list((Path(directory) / 'results').iterdir())), 1)
