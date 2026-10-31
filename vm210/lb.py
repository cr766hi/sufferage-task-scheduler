#!/usr/bin/env python3
"""Small experimental reverse proxy. Requires aiohttp and the optional backend CPU workers.

Latency includes the Sufferage batch wait. Capacity weights are model inputs,
not measured CPU capacity. No artificial processing delays are injected.
"""
import argparse
import asyncio
import csv
import itertools
import json
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout, TCPConnector, web


try:
    from vm_metrics import snapshot as resource_snapshot
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'monitoring'))
    from vm_metrics import snapshot as resource_snapshot

HOP_HEADERS = {'connection', 'keep-alive', 'proxy-authenticate',
               'proxy-authorization', 'te', 'trailer', 'transfer-encoding',
               'upgrade', 'content-length'}


@dataclass
class Backend:
    name: str
    url: str
    capacity: float
    healthy: bool = False
    active: int = 0
    ready_time: float = 0.0
    cooldown_until: float = 0.0
    task_url: str = ''


def sufferage_plan(jobs, backends, now):
    """Return (job, backend, predicted_seconds), updating virtual ready times.

    Jobs expose .work (seconds on a capacity-one backend) and .sequence.
    No await occurs during planning, so reservations are atomic on the event loop.
    """
    remaining = list(jobs)
    result = []
    while remaining:
        choices = []
        for job in remaining:
            times = sorted(
                ((max(now, b.ready_time) + job.work / b.capacity, i, b)
                 for i, b in enumerate(backends)), key=lambda item: (item[0], item[1]))
            best_ct, _, best = times[0]
            difference = times[1][0] - best_ct if len(times) > 1 else 0.0
            choices.append((difference, -job.sequence, job, best, best_ct))
        difference, _, job, best, best_ct = max(choices, key=lambda item: item[:2])
        job.sufferage_ms = difference * 1000
        job.best_ct_ms = (best_ct - now) * 1000
        job.second_ct_ms = (best_ct + difference - now) * 1000
        best.ready_time = best_ct
        result.append((job, best, job.work / best.capacity))
        remaining.remove(job)
    return result


@dataclass
class Job:
    sequence: int
    request: object
    body: bytes
    arrival: float
    timestamp: str
    work: float
    future: object
    task_type: str = ''
    sufferage_ms: float = 0.0
    best_ct_ms: float = 0.0
    second_ct_ms: float = 0.0
    batch_id: int = 0
    assignment_order: int = 0


class LoadBalancer:
    def __init__(self, args):
        self.args = args
        self.backends = [Backend('vm101', 'http://192.168.56.21', 1),
                         Backend('vm102', 'http://192.168.56.22', 2),
                         Backend('vm201', 'http://192.168.56.31', 1),
                         Backend('vm202', 'http://192.168.56.32', 2)]
        profile_path = Path(getattr(args, 'task_profiles', None) or Path(__file__).with_name('task_profiles.json'))
        if not profile_path.exists():
            profile_path = Path(__file__).resolve().parents[1] / 'workload/task_profiles.json'
        self.profile = json.loads(profile_path.read_text())
        self.task_profiles = self.profile['tasks']
        for backend in self.backends:
            if getattr(args, 'task_port', 0):
                backend.task_url = backend.url + ':' + str(args.task_port)
        self.batch_sequence = itertools.count(1)
        self.pending = asyncio.Queue(maxsize=args.queue_limit)
        self.sequence = itertools.count()
        self.rr = 0
        self.estimates = {}
        self.tasks = set()
        self.running = True
        path = Path(args.csv)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.log_file = path.open('x', newline='', encoding='utf-8')
        self.log = csv.writer(self.log_file)
        self.log.writerow(['timestamp', 'algoritma', 'backend', 'response_time_ms',
                           'status', 'request_id', 'method', 'path', 'queue_ms',
                           'upstream_ms', 'estimated_work_ms', 'error', 'task_type',
                           'sufferage_ms', 'best_ct_ms', 'second_ct_ms', 'batch_id', 'assignment_order'])
        self.log_file.flush()

    async def start(self, app):
        self.session = ClientSession(timeout=ClientTimeout(total=self.args.timeout),
                                     connector=TCPConnector(limit=128),
                                     auto_decompress=False, trust_env=False)
        await asyncio.gather(*(self.probe(b) for b in self.backends))
        self.background = [asyncio.create_task(self.scheduler()),
                           asyncio.create_task(self.health_loop())]

    async def stop(self, app):
        self.running = False
        for task in self.background:
            task.cancel()
        await asyncio.gather(*self.background, return_exceptions=True)
        while not self.pending.empty():
            job = self.pending.get_nowait()
            self.fail(job, 503, 'Proxy shutting down')
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.session.close()
        self.log_file.flush()
        self.log_file.close()

    async def probe(self, backend):
        if time.monotonic() < backend.cooldown_until:
            return
        try:
            async with self.session.get(backend.url + '/', timeout=ClientTimeout(total=1.5)) as response:
                await response.read()
                backend.healthy = response.status == 200
            if backend.healthy and backend.task_url:
                async with self.session.get(backend.task_url + '/health', timeout=ClientTimeout(total=2)) as response:
                    health = await response.json()
                    backend.healthy = (response.status == 200 and health.get('backend') == backend.name
                        and health.get('capacity') == backend.capacity
                        and health.get('workload') == self.profile['workload_id'])
        except (OSError, asyncio.TimeoutError) as exc:
            backend.healthy = False
        except Exception as exc:
            backend.healthy = False
            print('Health probe:', backend.name, repr(exc), flush=True)

    async def health_loop(self):
        while True:
            await asyncio.sleep(1)
            await asyncio.gather(*(self.probe(b) for b in self.backends))
            self.log_file.flush()

    async def metrics(self, request):
        try:
            return web.json_response(resource_snapshot('vm210'))
        except (OSError, ValueError, KeyError) as error:
            return web.json_response({'error': type(error).__name__ + ': ' + str(error)}, status=503)

    async def health(self, request):
        return web.json_response({'algorithm': self.args.mode,
                                  'queued': self.pending.qsize(),
                                  'workload': self.profile['workload_id'],
                                  'task_profiles': self.task_profiles,
                                  'work_estimates_ms': {key: round(value * 1000, 3) for key, value in self.estimates.items()},
                                  'backends': [{'name': b.name, 'healthy': b.healthy,
                                                'active': b.active, 'capacity': b.capacity}
                                               for b in self.backends]})

    def estimated_work(self, path):
        kind = path.removeprefix('/task/') if path.startswith('/task/') else ''
        initial_ms = self.task_profiles.get(kind, {}).get('initial_work_ms', self.args.initial_work_ms)
        return self.estimates.get(path, initial_ms / 1000)

    async def handle(self, request):
        now = time.monotonic()
        job = Job(next(self.sequence), request, await request.read(), now,
                  datetime.now(timezone.utc).isoformat(),
                  self.estimated_work(request.path),
                  asyncio.get_running_loop().create_future(),
                  task_type=request.path.removeprefix('/task/') if request.path.startswith('/task/') else '')
        try:
            self.pending.put_nowait(job)
        except asyncio.QueueFull:
            self.fail(job, 503, 'Admission queue full')
        return await asyncio.shield(job.future)

    def record(self, job, backend, status, queue_ms=0, upstream_ms=0, error=''):
        self.log.writerow([job.timestamp, self.args.mode, backend,
                           round((time.monotonic() - job.arrival) * 1000, 3), status,
                           job.request.headers.get('X-Request-ID', str(job.sequence)),
                           job.request.method, job.request.path_qs, round(queue_ms, 3),
                           round(upstream_ms, 3), round(job.work * 1000, 3), error,
                           job.task_type, round(job.sufferage_ms, 3), round(job.best_ct_ms, 3),
                           round(job.second_ct_ms, 3), job.batch_id, job.assignment_order])

    def fail(self, job, status, message):
        self.record(job, 'none', status, error=message)
        if not job.future.done():
            job.future.set_result(web.Response(status=status, text=message))

    async def scheduler(self):
        while True:
            first = await self.pending.get()
            batch = [first]
            if self.args.mode == 'sufferage':
                deadline = first.arrival + self.args.batch_ms / 1000
                while len(batch) < self.args.batch_size:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        batch.append(await asyncio.wait_for(self.pending.get(), remaining))
                    except asyncio.TimeoutError:
                        break
            batch_id = next(self.batch_sequence)
            for job in batch:
                job.batch_id = batch_id
            now = time.monotonic()
            available = [b for b in self.backends if b.healthy and b.cooldown_until <= now]
            if not available:
                for job in batch:
                    self.fail(job, 503, 'No healthy backend')
                continue
            if self.args.mode == 'sufferage':
                plan = sufferage_plan(batch, available, now)
                for order, (job, backend, predicted) in enumerate(plan, 1):
                    job.assignment_order = order
                    self.dispatch(job, backend, predicted)
            else:
                for job in batch:
                    if self.args.mode == 'round_robin':
                        backend = available[self.rr % len(available)]
                        self.rr += 1
                    else:
                        minimum = min(b.active for b in available)
                        ties = [b for b in available if b.active == minimum]
                        backend = ties[self.rr % len(ties)]
                        self.rr += 1
                    self.dispatch(job, backend, job.work / backend.capacity)

    def dispatch(self, job, backend, predicted):
        backend.active += 1
        task = asyncio.create_task(self.forward(job, backend, predicted))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def forward(self, job, backend, predicted):
        start = time.monotonic()
        queue_ms = (start - job.arrival) * 1000
        try:
            connection_tokens = {s.strip().lower() for s in job.request.headers.get('Connection', '').split(',')}
            headers = {k: v for k, v in job.request.headers.items()
                       if k.lower() not in HOP_HEADERS | connection_tokens | {'host'}}
            async with self.session.request(job.request.method,
                    (backend.task_url if job.task_type and backend.task_url else backend.url) + job.request.path_qs, headers=headers,
                    data=job.body or None, allow_redirects=False) as response:
                body = await response.read()
                elapsed = time.monotonic() - start
                response_connection = {s.strip().lower() for s in response.headers.get('Connection', '').split(',')}
                out_headers = {k: v for k, v in response.headers.items()
                               if k.lower() not in HOP_HEADERS | response_connection}
                out_headers['X-LB-Backend'] = backend.name
                out_headers['X-LB-Algorithm'] = self.args.mode
                out_headers.update({
                    'X-LB-Estimated-Work-Ms': str(round(job.work * 1000, 3)),
                    'X-LB-Queue-Ms': str(round(queue_ms, 3)),
                    'X-LB-Upstream-Ms': str(round(elapsed * 1000, 3)),
                    'X-LB-Sufferage-Ms': str(round(job.sufferage_ms, 3)),
                    'X-LB-Best-CT-Ms': str(round(job.best_ct_ms, 3)),
                    'X-LB-Second-CT-Ms': str(round(job.second_ct_ms, 3)),
                    'X-LB-Batch-ID': str(job.batch_id),
                    'X-LB-Assignment-Order': str(job.assignment_order)})
                result = web.Response(status=response.status, headers=out_headers, body=body)
                if response.status < 500:
                    previous = self.estimated_work(job.request.path)
                    observed_work = elapsed * backend.capacity
                    # CPU time summed across worker processes excludes waiting in the worker queue.
                    if job.task_type and response.status == 200:
                        try:
                            observed_work = max(.0001, float(response.headers['X-Worker-CPU-Ms']) / 1000)
                        except (KeyError, ValueError):
                            pass
                    self.estimates[job.request.path] = max(0.0001, .8 * previous + .2 * observed_work)
                self.record(job, backend.name, response.status, queue_ms, elapsed * 1000)
        except Exception as exc:
            backend.healthy = False
            backend.cooldown_until = time.monotonic() + 2
            self.record(job, backend.name, 502, queue_ms,
                        (time.monotonic() - start) * 1000,
                        type(exc).__name__ + ': ' + str(exc))
            result = web.Response(status=502, text='Upstream unavailable',
                                  headers={'X-LB-Backend': backend.name, 'X-LB-Algorithm': self.args.mode,
                                           'X-Task-Type': job.task_type,
                                           'X-LB-Estimated-Work-Ms': str(round(job.work * 1000, 3))})
        finally:
            backend.active -= 1
            backend.ready_time = max(time.monotonic(), backend.ready_time - predicted)
        if not job.future.done():
            job.future.set_result(result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['round_robin', 'least_connections', 'sufferage'])
    parser.add_argument('--port', type=int, default=80)
    parser.add_argument('--csv', required=True, help='New file; existing CSV is never overwritten')
    parser.add_argument('--batch-size', type=int, default=20)
    parser.add_argument('--batch-ms', type=float, default=75)
    parser.add_argument('--timeout', type=float, default=20)
    parser.add_argument('--task-port', type=int, default=8080)
    parser.add_argument('--task-profiles', type=Path)
    parser.add_argument('--initial-work-ms', type=float, default=20)
    parser.add_argument('--queue-limit', type=int, default=1000)
    args = parser.parse_args()
    if args.batch_size < 1 or args.batch_ms <= 0 or args.timeout <= 0:
        parser.error('batch-size, batch-ms and timeout must be positive')
    lb = LoadBalancer(args)
    app = web.Application(client_max_size=2 * 1024 * 1024)
    app.router.add_get('/__lb/health', lb.health)
    app.router.add_get('/__lb/metrics', lb.metrics)
    app.router.add_route('*', '/{tail:.*}', lb.handle)
    app.on_startup.append(lb.start)
    app.on_cleanup.append(lb.stop)
    web.run_app(app, host='0.0.0.0', port=args.port, shutdown_timeout=10)


if __name__ == '__main__':
    main()
