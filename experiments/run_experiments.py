"""Run real VM experiments from Windows; passwords are prompted, never saved.

Only VM 101 is stopped for fault tests. Proxmox hosts are never stopped.
Run with the project's work/venv/Scripts/python.exe (Locust + Paramiko).
"""
import argparse
import csv
import getpass
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
import paramiko

ROOT = Path(__file__).resolve().parents[1]
IPS = {'vm101': '192.168.56.21', 'vm102': '192.168.56.22',
       'vm201': '192.168.56.31', 'vm202': '192.168.56.32'}
MODES = ['round_robin', 'least_connections', 'sufferage']
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http(url, timeout=5):
    with HTTP.open(url, timeout=timeout) as response:
        return response.status, response.read().decode()


class Remote:
    def __init__(self, guest_password, host_password):
        self.passwords = {'guest': guest_password, 'host': host_password}
        self.clients = {}

    def client(self, ip):
        client = self.clients.get(ip)
        if client is None or not client.get_transport().is_active():
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(ip, username='root',
                           password=self.passwords['host' if ip in ('192.168.56.11','192.168.56.12') else 'guest'],
                           look_for_keys=False, allow_agent=False,
                           timeout=15, auth_timeout=25, banner_timeout=30)
            self.clients[ip] = client
        return client

    def cmd(self, ip, command, timeout=90):
        stdin, stdout, stderr = self.client(ip).exec_command(command, timeout=timeout)
        stdin.channel.shutdown_write()
        out = stdout.read().decode()
        err = stderr.read().decode()
        code = stdout.channel.recv_exit_status()
        if code:
            raise RuntimeError(f'{ip}: exit {code}: {err or out}')
        return out

    def put(self, local, remote):
        stdin, stdout, stderr = self.client('192.168.56.10').exec_command(
            'umask 077; cat > ' + shlex.quote(remote), timeout=60)
        stdin.write(Path(local).read_bytes())
        stdin.flush()
        stdin.channel.shutdown_write()
        if stdout.channel.recv_exit_status():
            raise RuntimeError(stderr.read().decode())

    def get(self, remote, local):
        data = self.cmd('192.168.56.10', 'cat ' + shlex.quote(remote))
        Path(local).write_text(data, encoding='utf-8')

    def close(self):
        for client in self.clients.values():
            client.close()


def wait_backends(seconds=150):
    deadline = time.monotonic() + seconds
    last = {}
    while time.monotonic() < deadline:
        for name, ip in IPS.items():
            try:
                status, body = http('http://' + ip + '/', timeout=3)
                last[name] = 'ok' if status == 200 and name in body else f'{status}: {body}'
            except Exception as exc:
                last[name] = f'{type(exc).__name__}: {exc}'
        if all(value == 'ok' for value in last.values()):
            return
        time.sleep(2)
    raise RuntimeError('Backend readiness failed: ' + json.dumps(last))


def wait_lb(mode, seconds=45):
    deadline = time.monotonic() + seconds
    last = ''
    while time.monotonic() < deadline:
        try:
            _, body = http('http://192.168.56.10/__lb/health', timeout=3)
            health = json.loads(body)
            if health['algorithm'] == mode and all(b['healthy'] for b in health['backends']):
                return health
            last = body
        except Exception as exc:
            last = str(exc)
        time.sleep(1)
    raise RuntimeError('LB readiness failed: ' + last)


def stop_lb(remote, base):
    # Verify ownership before sending SIGTERM to the PID recorded by this runner.
    command = f'''if test -f {shlex.quote(base + '/lb.pid')}; then
pid=$(cat {shlex.quote(base + '/lb.pid')})
if test -r /proc/$pid/cmdline && tr '\\000' ' ' < /proc/$pid/cmdline | grep -Fq {shlex.quote(base + '/lb.py')}; then
kill -TERM "$pid"
for i in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
fi
fi'''
    remote.cmd('192.168.56.10', command, timeout=35)


def start_lb(remote, base, mode, name):
    remote_csv = base + '/results/' + name + '-lb.csv'
    log = base + '/results/' + name + '-lb.log'
    command = ('nohup python3 -u ' + shlex.quote(base + '/lb.py') + ' ' + mode +
               ' --csv ' + shlex.quote(remote_csv) + ' > ' + shlex.quote(log) +
               ' 2>&1 < /dev/null & echo $! > ' + shlex.quote(base + '/lb.pid'))
    remote.cmd('192.168.56.10', command)
    return remote_csv, log


def config_snapshot(remote):
    result = {}
    for ip, ids in [('192.168.56.11', [101, 102]), ('192.168.56.12', [201, 202, 210])]:
        command = 'uptime; pvecm status; qm list; ' + '; '.join('qm config ' + str(i) for i in ids)
        result[ip] = remote.cmd(ip, command)
        if 'Quorate:          Yes' not in result[ip]:
            raise RuntimeError('Cluster has no quorum on ' + ip)
    for name, ip in IPS.items():
        result[name] = remote.cmd(ip, "hostname; getconf _NPROCESSORS_ONLN; cat /proc/cmdline")
        expected = 2 if name in ('vm102', 'vm202') else 1
        actual = int(result[name].splitlines()[1])
        if actual != expected:
            raise RuntimeError(f'{name}: expected {expected} vCPU, found {actual}')
    result['vm210'] = remote.cmd('192.168.56.10',
                                "hostname; python3 --version; python3 -c 'import aiohttp; print(aiohttp.__version__)'; date -u")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=int, default=60)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--scenarios', nargs='+', default=['stable', 'spike', 'fault'],
                        choices=['stable', 'spike', 'fault'])
    parser.add_argument('--session', default=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    parser.add_argument('--resume', action='store_true', help='Resume existing session, keeping completed measurements')
    args = parser.parse_args()
    if args.duration < 15 or args.repeats < 1:
        parser.error('duration >= 15 and repeats >= 1 required')
    if not args.session.replace('-', '').replace('_', '').isalnum():
        parser.error('session must be an alphanumeric identifier')
    directory = ROOT / 'results' / args.session
    if args.resume:
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        if (manifest['duration'], manifest['repeats'], manifest['scenarios']) != (args.duration, args.repeats, args.scenarios):
            parser.error('Resume requires the original duration, repeats and scenarios')
        manifest.setdefault('interruptions', []).append({'epoch': time.time(),
            'previous_status': manifest['status'], 'previous_error': manifest.pop('error', None)})
    else:
        directory.mkdir(parents=True, exist_ok=False)
        manifest = {'session': args.session, 'remote_directory': '/root/lb-experiment/' + args.session,
                    'duration': args.duration, 'repeats': args.repeats,
                    'scenarios': args.scenarios, 'runs': [], 'status': 'preflight'}
    guest = getpass.getpass('Alpine SSH password: ')
    host = getpass.getpass('Proxmox SSH password: ')
    remote = Remote(guest, host)
    del guest, host
    base = '/root/lb-experiment/' + args.session
    process = None
    backend_down = False
    deployed = False

    def save():
        (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')

    try:
        wait_backends(240)
        snapshot_name = ('infrastructure-resume' + str(len(manifest.get('interruptions', []))) + '.json') if args.resume else 'infrastructure.json'
        snapshot = config_snapshot(remote)
        (directory / snapshot_name).write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
        if args.resume and ' noapic' in snapshot['vm101']:
            manifest['post_test_recovery'] = {'vm101_temporary_kernel_option': 'noapic',
                'note': 'Applied interactively for a single boot after all workload measurements finished; boot configuration files were not changed.'}
        remote.cmd('192.168.56.10', 'mkdir -p ' + shlex.quote(base + '/results'))
        remote.put(ROOT / 'vm210/lb.py', base + '/lb.py')
        deployed = True
        manifest['status'] = 'running'
        if args.resume:
            # A measured run can be complete even when the subsequent VM boot fails.
            # Salvage only if both independent per-request logs match exactly.
            for previous in manifest['runs']:
                if previous['state'] == 'complete':
                    continue
                name = previous['name']
                client_csv = directory / (name + '-client.csv')
                metadata_path = client_csv.with_suffix('.json')
                if (previous.get('fault') or {}).get('restore_command_epoch') and client_csv.exists() and metadata_path.exists():
                    remote.get(base + '/results/' + name + '-lb.csv', directory / (name + '-lb.csv'))
                    remote.get(base + '/results/' + name + '-lb.log', directory / (name + '-lb.log'))
                    with client_csv.open(newline='', encoding='utf-8') as stream:
                        client_rows = list(csv.DictReader(stream))
                    with (directory / (name + '-lb.csv')).open(newline='', encoding='utf-8') as stream:
                        proxy_rows = list(csv.DictReader(stream))
                    ids = [r['request_id'] for r in client_rows]
                    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
                    locust_log = (directory / (name + '-locust.log')).read_text(encoding='utf-8')
                    if (len(client_rows) == len(proxy_rows) == len(set(ids)) and ids
                        and set(ids) == {r['request_id'] for r in proxy_rows}
                        and metadata['duration_seconds'] >= args.duration
                        and 'Shape test completed' in locust_log):
                        previous.update(state='complete', requests=len(client_rows),
                            errors=sum(bool(r['error']) or not 200 <= int(r['status']) < 400 for r in client_rows),
                            recovery_note='Measurement completed before VM 101 boot recovery timed out; manually reset VM 101 after console confirmed IO-APIC kernel panic. Independent request logs verified.')
                        previous['fault']['healthy_epoch'] = time.time()
                        previous['fault']['recovery_required_manual_reset'] = True
                        if ' noapic' in snapshot['vm101']:
                            previous['fault']['recovery_temporary_noapic'] = True
                        if 'ValueError: I/O operation on closed file.' in locust_log:
                            previous['stats_export_warning'] = 'Locust periodic CSV writer raised ValueError after test completion; final per-request logs verified.'
                        print('SALVAGED verified measurement', name, previous['requests'], flush=True)
                        continue
                previous['state'] = 'interrupted'
        save()
        for scenario in args.scenarios:
            for repeat in range(1, args.repeats + 1):
                modes = MODES[(repeat - 1) % 3:] + MODES[:(repeat - 1) % 3]
                for mode in modes:
                    if any(r['state'] == 'complete' and (r['scenario'], r['repeat'], r['algorithm']) == (scenario, repeat, mode) for r in manifest['runs']):
                        continue
                    wait_backends(150)
                    name = f'{scenario}-r{repeat}-{mode}'
                    attempt = 1
                    original_name = name
                    while any(r['name'] == name for r in manifest['runs']):
                        attempt += 1
                        name = original_name + '-attempt' + str(attempt)
                    print('START', name, flush=True)
                    stop_lb(remote, base)
                    remote_csv, remote_log = start_lb(remote, base, mode, name)
                    try:
                        wait_lb(mode)
                    except Exception:
                        print(remote.cmd('192.168.56.10', 'cat ' + shlex.quote(remote_log)), flush=True)
                        raise
                    # Readiness only uses the excluded health endpoint. Reset is a fresh process.
                    client_csv = directory / (name + '-client.csv')
                    env = os.environ.copy()
                    env.update(WORKLOAD='uniform', SCENARIO=scenario, DURATION=str(args.duration),
                               REQUEST_CSV=str(client_csv), RUN_SEED=str(1000 + repeat))
                    record = {'scenario': scenario, 'repeat': repeat, 'algorithm': mode,
                              'name': name, 'state': 'running', 'fault': None}
                    manifest['runs'].append(record)
                    save()
                    with (directory / (name + '-locust.log')).open('w', encoding='utf-8') as log:
                        process = subprocess.Popen([sys.executable, '-m', 'locust', '-f', str(ROOT / 'windows/locustfile.py'),
                            '--headless', '--only-summary', '--stop-timeout', '8',
                            '--csv', str(directory / name), '--host', 'http://192.168.56.10'],
                            env=env, stdout=log, stderr=subprocess.STDOUT)
                        launch = time.monotonic()
                        while process.poll() is None:
                            start_path = client_csv.with_suffix('.started.json')
                            if scenario == 'fault' and record['fault'] is None and start_path.exists():
                                started = json.loads(start_path.read_text())['epoch']
                                if time.time() - started >= args.duration / 2:
                                    fault = {'requested_epoch': time.time(), 'vmid': 101, 'host': 'pve1'}
                                    record['fault'] = fault
                                    backend_down = True
                                    save()
                                    remote.cmd('192.168.56.11', 'qm stop 101', timeout=70)
                                    fault['acknowledged_epoch'] = time.time()
                                    print('FAULT: VM 101 stopped', name, flush=True)
                                    save()
                            if time.monotonic() - launch > args.duration + 90:
                                raise RuntimeError('Locust exceeded the run deadline')
                            time.sleep(.5)
                        record['locust_exit'] = process.returncode
                        process = None
                    if backend_down:
                        remote.cmd('192.168.56.11', 'qm start 101', timeout=70)
                        record['fault']['restore_command_epoch'] = time.time()
                        backend_down = False
                        print('RESTORE: waiting for VM 101 boot', flush=True)
                        wait_backends(180)
                        record['fault']['healthy_epoch'] = time.time()
                    stop_lb(remote, base)
                    remote.get(remote_csv, directory / (name + '-lb.csv'))
                    remote.get(remote_log, directory / (name + '-lb.log'))
                    if not client_csv.exists() or not client_csv.with_suffix('.json').exists():
                        raise RuntimeError('Locust did not produce complete request data; see its log')
                    if scenario == 'fault' and record['fault'] is None:
                        raise RuntimeError('Fault was not injected; run is invalid')
                    with client_csv.open(newline='', encoding='utf-8') as stream:
                        rows = list(csv.DictReader(stream))
                    record.update(state='complete', requests=len(rows),
                                  errors=sum(bool(r['error']) or not 200 <= int(r['status']) < 400 for r in rows))
                    save()
                    print('DONE', name, 'requests', record['requests'], 'errors', record['errors'], flush=True)
        manifest['status'] = 'complete'
        # Leave a functional Sufferage instance on port 80 after collecting all runs.
        start_lb(remote, base, 'sufferage', 'live-sufferage')
        wait_lb('sufferage')
        manifest['live_algorithm'] = 'sufferage'
        save()
        print('COMPLETE', str(directory), flush=True)
    except BaseException as exc:
        manifest['status'] = 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed'
        manifest['error'] = type(exc).__name__ + ': ' + str(exc)
        save()
        print('ERROR', manifest['error'], flush=True)
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=15)
        if backend_down:
            try:
                state = remote.cmd('192.168.56.11', 'qm status 101')
                if 'stopped' in state:
                    remote.cmd('192.168.56.11', 'qm start 101', timeout=70)
                print('RESTORE command sent for VM 101', flush=True)
            except Exception as restore_error:
                print('RESTORE FAILED', str(restore_error), flush=True)
        if deployed:
            try:
                stop_lb(remote, base)
            except Exception as stop_error:
                print('LB STOP FAILED', str(stop_error), flush=True)
        raise
    finally:
        remote.close()


if __name__ == '__main__':
    main()
