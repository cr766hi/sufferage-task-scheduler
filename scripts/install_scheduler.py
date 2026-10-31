"""Install the batch scheduler on vm210; keep nginx and worker services unchanged."""
import getpass
import json
from pathlib import Path
import time
import urllib.request
import paramiko


def main():
    root = Path(__file__).resolve().parents[1]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    health_unknown = False
    try:
        with opener.open('http://192.168.56.10/api/health', timeout=5) as response:
            old = json.load(response)
        if old.get('active_batch'):
            raise RuntimeError('An active batch must finish before installation')
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    except urllib.error.URLError as error:
        health_unknown = True
        print('HTTP scheduler belum tersedia:', str(error), flush=True)
    files = [('vm210/scheduler.py','scheduler.py'), ('vm210/sufferage.py','sufferage.py'),
             ('monitoring/vm_metrics.py','vm_metrics.py'), ('monitoring/resource_stats.py','resource_stats.py'),
             ('workload/task_profiles.json','task_profiles.json'),
             ('vm210/openrc/task-scheduler','task-scheduler'),
             ('vm210/openrc/run-task-scheduler','run-task-scheduler')]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect('192.168.56.10', username='root', password=getpass.getpass('Alpine SSH password: '),
                       timeout=15, auth_timeout=25, banner_timeout=30, look_for_keys=False, allow_agent=False)
        def command(text):
            _, out, err = client.exec_command(text, timeout=180)
            output, error = out.read().decode(), err.read().decode()
            if out.channel.recv_exit_status():
                raise RuntimeError(error + output)
            return output
        if health_unknown:
            command('if test -x /etc/init.d/task-scheduler && rc-service task-scheduler status >/dev/null 2>&1; then echo Cannot verify active batch on existing scheduler >&2; exit 1; fi')
        command('mkdir -p /root/scheduler-install /opt/sufferage-scheduler /var/log/sufferage-scheduler')
        for source,name in files:
            stdin,out,err = client.exec_command('umask 077; cat > /root/scheduler-install/' + name, timeout=60)
            stdin.write((root/source).read_text(encoding='utf-8').replace('\r\n','\n').encode())
            stdin.flush()
            stdin.channel.shutdown_write()
            if out.channel.recv_exit_status():
                raise RuntimeError(err.read().decode())
        print(command('''set -eu
python3 -m py_compile /root/scheduler-install/scheduler.py /root/scheduler-install/sufferage.py /root/scheduler-install/vm_metrics.py /root/scheduler-install/resource_stats.py
sh -n /root/scheduler-install/task-scheduler
sh -n /root/scheduler-install/run-task-scheduler
if test -x /etc/init.d/sufferage-lb; then
    if rc-service sufferage-lb status >/dev/null 2>&1; then rc-service sufferage-lb stop; fi
    rc-update del sufferage-lb default || true
fi
if test -x /etc/init.d/task-scheduler && rc-service task-scheduler status >/dev/null 2>&1; then rc-service task-scheduler stop; fi
for item in scheduler.py sufferage.py vm_metrics.py resource_stats.py task_profiles.json; do
    if test -f /opt/sufferage-scheduler/$item; then cp -p /opt/sufferage-scheduler/$item /opt/sufferage-scheduler/$item.before-install; fi
    cp /root/scheduler-install/$item /opt/sufferage-scheduler/$item
    chmod 0644 /opt/sufferage-scheduler/$item
done
cp /root/scheduler-install/task-scheduler /etc/init.d/task-scheduler
cp /root/scheduler-install/run-task-scheduler /usr/local/sbin/run-task-scheduler
chmod 0755 /etc/init.d/task-scheduler /usr/local/sbin/run-task-scheduler
rc-update add task-scheduler default
rc-service task-scheduler start
rc-service task-scheduler status
'''), flush=True)
        for attempt in range(40):
            try:
                with opener.open('http://192.168.56.10/api/health', timeout=10) as response:
                    health = json.load(response)
                assert health['role'] == 'task_scheduler'
                assert all(worker['healthy'] for worker in health['workers'])
                print(json.dumps(health, indent=2), flush=True)
                return
            except Exception:
                if attempt == 39:
                    raise
                time.sleep(1)
    finally:
        client.close()


if __name__ == '__main__':
    main()
