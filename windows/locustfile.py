"""Controlled, closed-loop HTTP workload. SCENARIO=stable|spike|fault.

Fault injection is performed by the runner against VM 101, never a Proxmox host.
The request mix is intentionally the existing nginx root page: uniform work.
"""
import csv
import json
import os
import random
import time
from pathlib import Path
from locust import HttpUser, LoadTestShape, constant_pacing, events, task

SCENARIO = os.environ.get('SCENARIO', 'stable')
DURATION = int(os.environ.get('DURATION', '60'))
REQUEST_CSV = os.environ.get('REQUEST_CSV')
writer = None
handle = None
started = None


@events.test_start.add_listener
def open_log(environment, **kwargs):
    global writer, handle, started
    started = time.perf_counter()
    random.seed(int(os.environ.get('RUN_SEED', '1001')))
    if REQUEST_CSV:
        Path(REQUEST_CSV).parent.mkdir(parents=True, exist_ok=True)
        Path(REQUEST_CSV).with_suffix('.started.json').write_text(
            json.dumps({'epoch': time.time()}), encoding='utf-8')
    if REQUEST_CSV:
        path = Path(REQUEST_CSV)
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open('x', newline='', encoding='utf-8')
        writer = csv.writer(handle)
        writer.writerow(['timestamp', 'scenario', 'request_id', 'backend',
                         'response_time_ms', 'status', 'error'])


@events.request.add_listener
def request_log(request_type, name, response_time, response_length,
                exception, context, response=None, **kwargs):
    if writer:
        writer.writerow([time.time(), SCENARIO, context.get('request_id', ''),
                         response.headers.get('X-LB-Backend', 'none') if response is not None else 'none',
                         response_time, response.status_code if response is not None else 0,
                         str(exception) if exception else ''])


@events.test_stop.add_listener
def close_log(environment, **kwargs):
    if handle:
        handle.close()
    if REQUEST_CSV and started is not None:
        Path(REQUEST_CSV).with_suffix('.json').write_text(json.dumps({
            'scenario': SCENARIO, 'duration_seconds': time.perf_counter() - started,
            'nominal_duration_seconds': DURATION,
            'users_base': 10, 'users_spike': 40, 'pacing_seconds': 1,
            'seed': int(os.environ.get('RUN_SEED', '1001')),
        }, indent=2), encoding='utf-8')


class BrowserUser(HttpUser):
    host = 'http://192.168.56.10'
    wait_time = constant_pacing(1)

    def on_start(self):
        self.client.trust_env = False
        self.counter = 0
        self.user_id = random.getrandbits(48)

    @task
    def homepage(self):
        self.counter += 1
        request_id = f'{self.user_id:x}-{self.counter}'
        with self.client.get('/', timeout=8, name='nginx root',
                             headers={'X-Request-ID': request_id},
                             context={'request_id': request_id},
                             catch_response=True) as response:
            if response.status_code == 200 and not any(
                    name in response.text for name in ('vm101', 'vm102', 'vm201', 'vm202')):
                response.failure('Unexpected backend page')


class ScenarioShape(LoadTestShape):
    def tick(self):
        elapsed = self.get_run_time()
        if elapsed >= DURATION:
            return None
        users = 10
        if SCENARIO == 'spike' and DURATION / 3 <= elapsed < 2 * DURATION / 3:
            users = 40
        return users, 40
