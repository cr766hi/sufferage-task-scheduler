"""Install stdlib CPU workers on the four backends without changing nginx."""
import getpass
import json
from pathlib import Path
import time
import urllib.request
import paramiko

BACKENDS = [('vm101', '192.168.56.21', 1), ('vm102', '192.168.56.22', 2),
            ('vm201', '192.168.56.31', 1), ('vm202', '192.168.56.32', 2)]


def main():
    root = Path(__file__).resolve().parents[1]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    password = getpass.getpass('Alpine SSH password: ')
    for name, ip, capacity in BACKENDS:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(ip, username='root', password=password, timeout=15,
                           banner_timeout=30, auth_timeout=25, look_for_keys=False, allow_agent=False)

            def command(text, timeout=180):
                _, out, err = client.exec_command(text, timeout=timeout)
                output = out.read().decode()
                error = err.read().decode()
                if out.channel.recv_exit_status():
                    raise RuntimeError(name + ': ' + error + output)
                return output

            print(name, command('command -v python3 || apk add --no-cache python3', 240), flush=True)
            command('mkdir -p /root/task-worker-install /opt/task-worker')
            for local, remote in [('backends/worker/worker.py', 'worker.py'),
                                  ('monitoring/vm_metrics.py', 'vm_metrics.py'),
                                  ('backends/worker/task-worker', 'task-worker'),
                                  ('workload/task_profiles.json', 'task_profiles.json')]:
                stdin, out, err = client.exec_command('umask 077; cat > /root/task-worker-install/' + remote)
                stdin.write((root / local).read_text(encoding='utf-8').replace('\r\n', '\n').encode())
                stdin.flush()
                stdin.channel.shutdown_write()
                if out.channel.recv_exit_status():
                    raise RuntimeError(name + ': ' + err.read().decode())
            script = '''set -eu
python3 -m py_compile /root/task-worker-install/worker.py /root/task-worker-install/vm_metrics.py
sh -n /root/task-worker-install/task-worker
if test -x /etc/init.d/task-worker && rc-service task-worker status >/dev/null 2>&1; then rc-service task-worker stop; fi
for item in /opt/task-worker/worker.py /opt/task-worker/task_profiles.json /etc/init.d/task-worker /etc/conf.d/task-worker; do
    if test -f "$item" && ! test -f "$item.before-cpu-install"; then cp -p "$item" "$item.before-cpu-install"; fi
done
cp /root/task-worker-install/vm_metrics.py /opt/task-worker/vm_metrics.py
cp /root/task-worker-install/worker.py /opt/task-worker/worker.py
cp /root/task-worker-install/task_profiles.json /opt/task-worker/task_profiles.json
cp /root/task-worker-install/task-worker /etc/init.d/task-worker
chmod 0755 /etc/init.d/task-worker
chmod 0644 /opt/task-worker/worker.py /opt/task-worker/task_profiles.json
'''
            script += f"printf 'backend_name={name}\\nworker_capacity={capacity}\\n' > /etc/conf.d/task-worker\n"
            script += 'rc-update add task-worker default\nrc-service task-worker start\nrc-service task-worker status\n'
            print(name, command(script), flush=True)
            for attempt in range(30):
                try:
                    with opener.open(f'http://{ip}:8080/health', timeout=5) as response:
                        health = json.load(response)
                    assert health['backend'] == name and health['capacity'] == capacity
                    print(name, 'worker ready', json.dumps(health), flush=True)
                    break
                except Exception:
                    if attempt == 29:
                        raise
                    time.sleep(1)
        finally:
            client.close()
    del password


if __name__ == '__main__':
    main()
