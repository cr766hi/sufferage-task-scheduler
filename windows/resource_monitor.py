"""Poll VM resource endpoints outside Locust request statistics."""
import time
import gevent
import requests

TARGETS = {
    'vm101': 'http://192.168.56.21:8080/metrics',
    'vm102': 'http://192.168.56.22:8080/metrics',
    'vm201': 'http://192.168.56.31:8080/metrics',
    'vm202': 'http://192.168.56.32:8080/metrics',
    'vm210': 'http://192.168.56.10/__lb/metrics',
}


def delta(previous, current):
    if not previous or previous['boot_id'] != current['boot_id']:
        return {}
    total = current['cpu_total_ticks'] - previous['cpu_total_ticks']
    busy = current['cpu_busy_ticks'] - previous['cpu_busy_ticks']
    seconds = current['sample_monotonic_seconds'] - previous['sample_monotonic_seconds']
    if total <= 0 or busy < 0 or busy > total or seconds <= 0:
        return {}
    return {'cpu_percent': 100 * busy / total, 'cpu_busy_delta_ticks': busy,
            'cpu_total_delta_ticks': total, 'resource_interval_seconds': seconds}


class ResourceMonitor:
    def __init__(self, report, targets=None, interval=2):
        self.report = report
        self.targets = TARGETS if targets is None else targets
        self.interval = interval
        self.previous = {}
        self.inflight = []
        self.loop = None
        self.failed = set()

    def start(self):
        self.loop = gevent.spawn(self.run)

    def fetch(self, vm, url):
        try:
            with requests.Session() as session:
                session.trust_env = False
                response = session.get(url, timeout=(1, 2))
                response.raise_for_status()
                current = response.json()
            if current['vm'] != vm:
                raise ValueError('Metric VM identity mismatch')
            sample = {'backend': vm, 'resource_status': 'ok',
                      'resource_source_timestamp_utc': current['timestamp_utc'],
                      **{field: current[field] for field in
                         ('vcpus', 'ram_total_mb', 'ram_used_mb', 'ram_available_mb', 'ram_percent')},
                      **delta(self.previous.get(vm), current)}
            self.previous[vm] = current
            if vm in self.failed:
                print(f"Resource monitor {vm}: pulih", flush=True)
                self.failed.discard(vm)
        except Exception as error:
            self.previous.pop(vm, None)
            if vm not in self.failed:
                print(f'Resource monitor {vm}: {type(error).__name__}: {error}', flush=True)
                self.failed.add(vm)
            sample = {'backend': vm, 'resource_status': 'error',
                      'error': type(error).__name__ + ': ' + str(error)}
        self.report.resource(sample)

    def run(self):
        next_sample = time.monotonic()
        while True:
            self.inflight = [gevent.spawn(self.fetch, vm, url) for vm, url in self.targets.items()]
            gevent.joinall(self.inflight)
            self.inflight = []
            next_sample = max(next_sample + self.interval, time.monotonic())
            gevent.sleep(max(0, next_sample - time.monotonic()))

    def stop(self):
        if self.loop is not None:
            self.loop.kill(block=True)
            self.loop = None
        gevent.killall(self.inflight, block=True)
        self.inflight = []
