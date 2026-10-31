#!/usr/bin/env python3
"""Bounded CPU workload service; stdlib only, separate from nginx."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import multiprocessing
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit


def compute_units(indices, iterations):
    started = time.process_time()
    checksum = 0
    for index in indices:
        digest = hashlib.pbkdf2_hmac('sha256', f'unit-{index}'.encode(),
                                     b'sufferage-lab-fixed-salt', iterations)
        checksum = (checksum + int.from_bytes(digest, 'big')) % (1 << 256)
    return checksum, (time.process_time() - started) * 1000


class WorkerServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, backend, capacity, profiles):
        super().__init__(address, Handler)
        self.backend = backend
        self.capacity = capacity
        self.profiles = profiles
        self.pool = ProcessPoolExecutor(max_workers=capacity,
                                       mp_context=multiprocessing.get_context('spawn'))
        self.admission = threading.BoundedSemaphore(24)

    def server_close(self):
        super().server_close()
        self.pool.shutdown(wait=True, cancel_futures=True)


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, payload, headers=None):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, str(value))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = urlsplit(self.path).path
        common = dict(backend=self.server.backend, capacity=self.server.capacity,
                      workload=self.server.profiles['workload_id'])
        if path == '/health':
            self.respond(200, {**common, 'tasks': self.server.profiles['tasks']})
            return
        kind = path.removeprefix('/task/') if path.startswith('/task/') else ''
        definition = self.server.profiles['tasks'].get(kind)
        if not definition:
            self.respond(404, {'error': 'Use /health or /task/light|medium|heavy'})
            return
        if not self.server.admission.acquire(blocking=False):
            self.respond(503, {**common, 'error': 'Worker admission limit reached'})
            return
        started = time.monotonic()
        try:
            units = definition['units']
            count = min(self.server.capacity, units)
            futures = [self.server.pool.submit(
                compute_units, list(range(index, units, count)),
                self.server.profiles['iterations_per_unit']) for index in range(count)]
            results = [future.result() for future in futures]
            cpu_ms = sum(result[1] for result in results)
            elapsed_ms = (time.monotonic() - started) * 1000
            checksum = sum(result[0] for result in results) % (1 << 256)
            self.respond(200, {**common, 'task_type': kind, 'units': units,
                'iterations_per_unit': self.server.profiles['iterations_per_unit'],
                'cpu_ms': round(cpu_ms, 3), 'worker_elapsed_ms': round(elapsed_ms, 3),
                'checksum': f'{checksum:064x}'}, {
                'X-Task-Type': kind, 'X-Task-Units': units,
                'X-Worker-CPU-Ms': round(cpu_ms, 3),
                'X-Worker-Elapsed-Ms': round(elapsed_ms, 3)})
        except Exception as error:
            print(type(error).__name__, str(error), flush=True)
            self.respond(500, {**common, 'error': type(error).__name__})
        finally:
            self.server.admission.release()

    def log_message(self, fmt, *args):
        if not self.path.startswith('/health'):
            print(self.address_string(), fmt % args, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--backend', required=True)
    parser.add_argument('--capacity', type=int, choices=(1, 2), required=True)
    parser.add_argument('--profiles', type=Path,
                        default=Path(__file__).with_name('task_profiles.json'))
    args = parser.parse_args()
    profiles = json.loads(args.profiles.read_text())
    with WorkerServer(('0.0.0.0', args.port), args.backend, args.capacity, profiles) as server:
        print(f'{args.backend}: CPU worker :{args.port}, processes={args.capacity}', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
