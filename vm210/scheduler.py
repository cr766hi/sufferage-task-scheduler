#!/usr/bin/env python3
"""Batch task scheduler. HTTP carries control messages and task RPC, not user traffic."""
import argparse
import asyncio
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys
import time
import uuid
from aiohttp import ClientSession, ClientTimeout, TCPConnector, web

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sufferage import sufferage_plan
try:
    from vm_metrics import snapshot
    from resource_stats import cpu_delta, summarize_resources
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'monitoring'))
    from vm_metrics import snapshot
    from resource_stats import cpu_delta, summarize_resources

WORKERS = [dict(name='vm101', url='http://192.168.56.21:8080', capacity=1),
           dict(name='vm102', url='http://192.168.56.22:8080', capacity=2),
           dict(name='vm201', url='http://192.168.56.31:8080', capacity=1),
           dict(name='vm202', url='http://192.168.56.32:8080', capacity=2)]
TASK_FIELDS = ['task_id','task_type','units','worker','allocation_order','etc_ms',
    'best_ct_ms','second_ct_ms','sufferage_ms','predicted_start_ms','predicted_finish_ms',
    'candidate_ct_ms','status','arrival_ms','start_ms','finish_ms','waiting_ms',
    'execution_ms','turnaround_ms','worker_cpu_ms','worker_elapsed_ms','checksum','error']
TERMINAL = {'completed','completed_with_errors','failed'}


def utc():
    return datetime.now(timezone.utc).isoformat()


def validate_tasks(tasks, profiles):
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 500:
        raise ValueError('Submit 1..500 tasks')
    validated, seen = [], set()
    for task in tasks:
        task_id, kind = str(task.get('task_id','')), task.get('task_type')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', task_id) or task_id in seen:
            raise ValueError('Task IDs must be unique, 1..64 letters/digits/_/-')
        if kind not in profiles['tasks']:
            raise ValueError('Unknown task type: ' + str(kind))
        units = profiles['tasks'][kind]['units']
        if int(task.get('units', units)) != units:
            raise ValueError('Task units must match the task profile')
        seen.add(task_id)
        validated.append(dict(task_id=task_id, task_type=kind, units=units))
    return validated


def batch_summary(batch):
    done = [task for task in batch['tasks'] if task['status'] == 'completed']
    attempted = [task for task in batch['tasks'] if task.get('finish_ms') is not None]
    # All tasks arrive together at batch admission; the last terminal event defines makespan.
    makespan_ms = batch['makespan_ms']
    waiting = [task['waiting_ms'] for task in done]
    turnaround = sorted(task['turnaround_ms'] for task in done)
    counts = [sum(task['worker'] == worker['name'] for task in batch['tasks']) for worker in batch['workers']]
    errors = [100 * abs(task['execution_ms'] - task['etc_ms']) / task['execution_ms']
              for task in done if task['execution_ms'] > 0]
    finishes = [max((task['finish_ms'] for task in done if task['worker'] == worker['name']), default=None)
                for worker in batch['workers']]
    finishes = [finish for finish in finishes if finish is not None]

    return dict(total_tasks=len(batch['tasks']), completed_tasks=len(done),
        failed_tasks=sum(task['status'] == 'failed' for task in batch['tasks']),
        skipped_tasks=sum(task['status'] == 'skipped' for task in batch['tasks']),
        success_rate_percent=100 * len(done) / len(batch['tasks']),
        makespan_seconds=makespan_ms / 1000, planning_ms=batch['planning_ms'],
        predicted_makespan_seconds=max(task['predicted_finish_ms'] for task in batch['tasks']) / 1000,
        execution_start_ms=batch.get('execution_start_ms', 0),
        execution_phase_seconds=(makespan_ms - batch.get('execution_start_ms', 0)) / 1000,
        predicted_batch_makespan_seconds=(batch.get('execution_start_ms', 0) + max(task['predicted_finish_ms'] for task in batch['tasks'])) / 1000,
        execution_prediction_mape_percent=statistics.mean(errors) if errors else None,
        worker_finish_spread_seconds=(max(finishes) - min(finishes)) / 1000 if finishes else None,

        avg_waiting_ms=statistics.mean(waiting) if waiting else None,
        avg_turnaround_ms=statistics.mean(turnaround) if turnaround else None,
        p95_turnaround_ms=turnaround[math.ceil(.95 * len(turnaround)) - 1] if turnaround else None,
        throughput_tasks_per_second=len(done) / (makespan_ms / 1000) if makespan_ms else 0,
        allocation_count_stddev=statistics.pstdev(counts))


class Scheduler:
    def __init__(self, profiles, log_root, workers=None):
        self.profiles = profiles
        self.log_root = Path(log_root)
        self.workers = WORKERS if workers is None else workers
        self.calibration = None
        self.batches = {}
        self.active = None
        self.control = asyncio.Lock()
        self.execution = None

    async def start(self, app):
        self.session = ClientSession(trust_env=False,
            timeout=ClientTimeout(total=60), connector=TCPConnector(limit=16))
        self.log_root.mkdir(parents=True, exist_ok=True)

    async def stop(self, app):
        if self.execution and not self.execution.done():
            await self.execution
        await self.session.close()

    async def worker_health(self, worker):
        try:
            async with self.session.get(worker['url'] + '/health', timeout=ClientTimeout(total=4)) as response:
                data = await response.json()
                valid = (response.status == 200 and data.get('backend') == worker['name']
                    and data.get('capacity') == worker['capacity']
                    and data.get('workload') == self.profiles['workload_id'])
                return {**worker, 'healthy': valid, 'error': '' if valid else 'Worker identity/profile mismatch'}
        except Exception as error:
            return {**worker, 'healthy': False, 'error': type(error).__name__ + ': ' + str(error)}

    async def health(self, request):
        workers = await asyncio.gather(*(self.worker_health(worker) for worker in self.workers))
        return web.json_response(dict(role='task_scheduler', algorithm='sufferage',
            scheduling='offline_batch', active_batch=self.active,
            calibrated=self.calibration is not None,
            calibration_version=self.calibration.get('version','worker-elapsed-median2-v1') if self.calibration else None, workers=workers))

    async def metrics(self, request):
        return web.json_response(snapshot('vm210'))

    async def worker_task(self, worker, kind):
        async with self.session.get(worker['url'] + '/task/' + kind) as response:
            data = await response.json()
            if response.status != 200:
                raise RuntimeError(f"{worker['name']}: HTTP {response.status}: {data}")
            if (data.get('backend') != worker['name'] or data.get('task_type') != kind
                    or data.get('units') != self.profiles['tasks'][kind]['units']
                    or data.get('workload') != self.profiles['workload_id']
                    or not re.fullmatch('[0-9a-f]{64}', data.get('checksum',''))):
                raise ValueError('Invalid worker task result')
            return data

    async def calibrate(self, request):
        async with self.control:
            if self.active:
                raise web.HTTPConflict(text='A batch is still running')
            health = await asyncio.gather(*(self.worker_health(worker) for worker in self.workers))
            if not all(worker['healthy'] for worker in health):
                return web.json_response({'error':'Workers not ready','workers':health}, status=503)
            kinds = list(self.profiles['tasks'])
            samples_per_cell = 7
            async def measure(worker, offset):
                # Warm every kind, including child process startup, outside measured samples.
                for kind in kinds:
                    await self.worker_task(worker, kind)
                values = {kind: [] for kind in kinds}
                worker_values = {kind: [] for kind in kinds}
                for repeat in range(samples_per_cell):
                    # Staggered mixed order better resembles the actual concurrent queues.
                    order = kinds[(offset + repeat) % len(kinds):] + kinds[:(offset + repeat) % len(kinds)]
                    for kind in order:
                        started = time.monotonic()
                        result = await self.worker_task(worker, kind)
                        elapsed_ms = (time.monotonic() - started) * 1000
                        values[kind].append(max(.001, elapsed_ms))
                        worker_values[kind].append(result['worker_elapsed_ms'])
                return worker['name'], values, worker_values
            calibration_resources = {'resources': []}
            previous = {}
            calibration_started = time.monotonic()
            stopped = asyncio.Event()
            monitoring = None
            try:
                await self.collect(calibration_resources, previous, calibration_started)
                monitoring = asyncio.create_task(self.monitor(calibration_resources, previous, calibration_started, stopped))
                measured = await asyncio.gather(*(measure(worker, index) for index, worker in enumerate(self.workers)), return_exceptions=True)
                failures = [value for value in measured if isinstance(value, BaseException)]
                if failures:
                    error = failures[0]
                    return web.json_response({'error':type(error).__name__ + ': ' + str(error)}, status=502)
            finally:
                stopped.set()
                if monitoring:
                    await monitoring
            matrix = {kind: {name: statistics.median(values[kind]) for name, values, _ in measured} for kind in kinds}
            details = {kind: {name: {
                'rpc_samples_ms': values[kind],
                'worker_samples_ms': worker_values[kind],
                'rpc_median_ms': statistics.median(values[kind]),
                'rpc_p90_ms': sorted(values[kind])[math.ceil(.9 * samples_per_cell) - 1],
                'rpc_cv_percent': 100 * statistics.pstdev(values[kind]) / statistics.mean(values[kind])
            } for name, values, worker_values in measured} for kind in kinds}
            self.calibration = dict(id='etc-' + uuid.uuid4().hex[:8], timestamp_utc=utc(),
                version='rpc-median7-v2', samples_per_cell=samples_per_cell,
                duration_seconds=time.monotonic() - calibration_started,
                method='median of 7 scheduler-observed RPC elapsed_ms per task type/worker; all types warmed; staggered mixed order; concurrent workers and resource polling',
                sample_details=details, etc_ms=matrix)
            print(json.dumps({'event':'calibrated', **self.calibration}), flush=True)
            return web.json_response(self.calibration)

    async def submit(self, request):
        async with self.control:
            if self.active:
                raise web.HTTPConflict(text='Only one batch can run at a time')
            if not self.calibration:
                raise web.HTTPConflict(text='Calibrate the ETC matrix before submitting a batch')
            try:
                payload = await request.json()
                tasks = validate_tasks(payload.get('tasks'), self.profiles)
            except (ValueError, TypeError, AttributeError) as error:
                raise web.HTTPBadRequest(text=str(error))
            health = await asyncio.gather(*(self.worker_health(worker) for worker in self.workers))
            if not all(worker['healthy'] for worker in health):
                return web.json_response({'error':'Workers not ready','workers':health}, status=503)
            run_id = 'batch-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:6]
            admitted = time.monotonic()
            plan = sufferage_plan(tasks, [worker['name'] for worker in self.workers], self.calibration['etc_ms'])
            planning_ms = (time.monotonic() - admitted) * 1000
            for task in plan:
                task.update(status='queued', arrival_ms=0, start_ms=None, finish_ms=None, error='')
            batch = dict(batch_id=run_id, status='running', algorithm='sufferage',
                scheduling='offline_batch', dataset_name=str(payload.get('dataset_name','dataset'))[:128],
                dataset_sha256=str(payload.get('dataset_sha256',''))[:64],
                admitted_at_utc=utc(), planning_ms=planning_ms,
                calibration=json.loads(json.dumps(self.calibration)), workers=self.workers,
                tasks=plan, resources=[], resource_summaries=[], summary=None,
                log_directory=str(self.log_root / run_id))
            self.batches[run_id] = batch
            self.active = run_id
            self.execution = asyncio.create_task(self.execute(batch, admitted))
            return web.json_response({'batch_id':run_id,'status':'running','total_tasks':len(tasks)}, status=202)

    async def collect(self, batch, previous, admitted):
        async def sample(vm, url=None):
            try:
                if url:
                    async with self.session.get(url + '/metrics', timeout=ClientTimeout(total=3)) as response:
                        if response.status != 200:
                            raise RuntimeError('Metrics HTTP ' + str(response.status))
                        current = await response.json()
                else:
                    current = snapshot('vm210')
                if current['vm'] != vm:
                    raise ValueError('Resource VM identity mismatch')
                result = dict(vm=vm, resource_status='ok', timestamp_utc=current['timestamp_utc'],
                    elapsed_ms=(time.monotonic() - admitted) * 1000,
                    **{key: current[key] for key in ('vcpus','ram_percent','ram_used_mb','ram_total_mb')},
                    **cpu_delta(previous.get(vm), current))
                previous[vm] = current
            except Exception as error:
                previous.pop(vm, None)
                result = dict(vm=vm, resource_status='error', timestamp_utc=utc(),
                    elapsed_ms=(time.monotonic() - admitted) * 1000,
                    error=type(error).__name__ + ': ' + str(error))
                print(json.dumps({'event':'resource_error', **result}), flush=True)
            batch['resources'].append(result)
        await asyncio.gather(*(sample(worker['name'], worker['url']) for worker in self.workers), sample('vm210'))

    async def monitor(self, batch, previous, admitted, stopped):
        while not stopped.is_set():
            try:
                await asyncio.wait_for(stopped.wait(), timeout=2)
            except asyncio.TimeoutError:
                await self.collect(batch, previous, admitted)

    async def execute(self, batch, admitted):
        directory = Path(batch['log_directory'])
        directory.mkdir(parents=True, exist_ok=False)
        stopped = asyncio.Event()
        monitoring = None
        terminal_status = 'failed'
        with (directory / 'tasks.csv').open('x', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=TASK_FIELDS, extrasaction='ignore')
            writer.writeheader()
            def record(task):
                writer.writerow({**task, 'candidate_ct_ms':json.dumps(task['candidate_ct_ms'], sort_keys=True)})
                handle.flush()
                print(json.dumps({'event':'task_terminal', 'batch_id':batch['batch_id'],
                                  **{key: task.get(key) for key in ('task_id','task_type','worker','status','waiting_ms','execution_ms','turnaround_ms')}}), flush=True)
            try:
                previous = {}
                await self.collect(batch, previous, admitted)
                batch['execution_start_ms'] = (time.monotonic() - admitted) * 1000
                monitoring = asyncio.create_task(self.monitor(batch, previous, admitted, stopped))
                async def execute_queue(worker):
                    unavailable = False
                    for task in [task for task in batch['tasks'] if task['worker'] == worker['name']]:
                        if unavailable:
                            task.update(status='skipped', error='Worker failed earlier; no automatic retry or reassignment')
                            record(task)
                            continue
                        task.update(status='running', start_ms=(time.monotonic() - admitted) * 1000)
                        task['waiting_ms'] = task['start_ms']  # All arrivals are zero.
                        print(json.dumps({'event':'task_started','batch_id':batch['batch_id'],
                                          'task_id':task['task_id'],'worker':worker['name']}), flush=True)
                        try:
                            result = await self.worker_task(worker, task['task_type'])
                            task.update(status='completed', worker_cpu_ms=result['cpu_ms'],
                                worker_elapsed_ms=result['worker_elapsed_ms'], checksum=result['checksum'])
                        except Exception as error:
                            task.update(status='failed', error=type(error).__name__ + ': ' + str(error))
                            unavailable = True
                        task['finish_ms'] = (time.monotonic() - admitted) * 1000
                        task['execution_ms'] = task['finish_ms'] - task['start_ms']
                        task['turnaround_ms'] = task['finish_ms']
                        record(task)
                await asyncio.gather(*(execute_queue(worker) for worker in self.workers))
                batch['makespan_ms'] = (time.monotonic() - admitted) * 1000
                batch['summary'] = batch_summary(batch)
                terminal_status = 'completed' if batch['summary']['completed_tasks'] == len(batch['tasks']) else 'completed_with_errors'
            except Exception as error:
                batch.update(error=type(error).__name__ + ': ' + str(error))
                print(json.dumps({'event':'batch_error','error':batch['error']}), flush=True)
            finally:
                stopped.set()
                if monitoring:
                    await monitoring
                batch['resource_summaries'] = summarize_resources(batch['resources'])
                batch['status'] = terminal_status
                batch['finished_at_utc'] = utc()
                # The completed result survives a scheduler restart and is retrievable by ID.
                (directory / 'result.json').write_text(json.dumps(batch, indent=2), encoding='utf-8')
                self.active = None
                print(json.dumps({'event':'batch_finished','batch_id':batch['batch_id'],
                                  'status':batch['status'],'summary':batch['summary']}), flush=True)

    async def result(self, request):
        run_id = request.match_info['batch_id']
        if run_id == 'latest':
            if self.batches:
                run_id = next(reversed(self.batches))
            else:
                saved = sorted(self.log_root.glob('batch-*/result.json'))
                if not saved:
                    raise web.HTTPNotFound(text='No batches yet')
                run_id = saved[-1].parent.name
        batch = self.batches.get(run_id)
        if batch is None:
            if not re.fullmatch(r'batch-[A-Za-z0-9-]+', run_id):
                raise web.HTTPBadRequest(text='Invalid batch ID')
            path = self.log_root / run_id / 'result.json'
            if not path.exists():
                raise web.HTTPNotFound(text='Batch not found')
            batch = json.loads(path.read_text())
        if request.query.get('summary') == '1':
            return web.json_response(dict(batch_id=run_id, status=batch['status'], total_tasks=len(batch['tasks']),
                terminal_tasks=sum(task['status'] in ('completed','failed','skipped') for task in batch['tasks']),
                summary=batch['summary'], error=batch.get('error','')))
        return web.json_response(batch)


def create_app(scheduler):
    app = web.Application(client_max_size=1024*1024)
    app.router.add_get('/', scheduler.health)
    app.router.add_get('/api/health', scheduler.health)
    app.router.add_get('/api/metrics', scheduler.metrics)
    app.router.add_post('/api/calibrate', scheduler.calibrate)
    app.router.add_post('/api/batches', scheduler.submit)
    app.router.add_get('/api/batches/{batch_id}', scheduler.result)
    app.on_startup.append(scheduler.start)
    app.on_cleanup.append(scheduler.stop)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=80)
    parser.add_argument('--log-root', type=Path, default=Path('/var/log/sufferage-scheduler'))
    parser.add_argument('--profiles', type=Path, default=Path(__file__).with_name('task_profiles.json'))
    args = parser.parse_args()
    profiles = json.loads(args.profiles.read_text())
    web.run_app(create_app(Scheduler(profiles, args.log_root)), host='0.0.0.0', port=args.port, shutdown_timeout=90)


if __name__ == '__main__':
    main()
