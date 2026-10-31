"""Install this repo's Sufferage service on vm210; credentials are only in memory."""
import argparse
import getpass
import json
from pathlib import Path
import time
import urllib.request
import paramiko


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='192.168.56.10')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    password = getpass.getpass('Alpine SSH password: ')
    try:
        client.connect(args.host, username='root', password=password, timeout=15,
                       banner_timeout=30, auth_timeout=25, look_for_keys=False, allow_agent=False)
        del password

        def command(text, timeout=90):
            stdin, stdout, stderr = client.exec_command(text, timeout=timeout)
            stdin.channel.shutdown_write()
            output = stdout.read().decode()
            error = stderr.read().decode()
            if stdout.channel.recv_exit_status():
                raise RuntimeError(error or output)
            return output

        print(command("hostname; command -v openrc-run; command -v supervise-daemon; python3 -c 'import aiohttp; print(aiohttp.__version__)'"))
        command('mkdir -p /root/sufferage-lb-install /opt/sufferage-lb /usr/local/sbin /var/log/sufferage-lb')
        for local, name in [(root / 'vm210/lb.py', 'lb.py'),
                            (root / 'vm210/openrc/sufferage-lb', 'sufferage-lb'),
                            (root / 'vm210/openrc/run-sufferage-lb', 'run-sufferage-lb')]:
            stdin, stdout, stderr = client.exec_command('umask 077; cat > /root/sufferage-lb-install/' + name, timeout=60)
            stdin.write(local.read_text(encoding='utf-8').replace('\r\n', '\n').encode('utf-8'))
            stdin.flush()
            stdin.channel.shutdown_write()
            if stdout.channel.recv_exit_status():
                raise RuntimeError(stderr.read().decode())
        print(command('''set -eu
sh -n /root/sufferage-lb-install/sufferage-lb
sh -n /root/sufferage-lb-install/run-sufferage-lb
python3 -m py_compile /root/sufferage-lb-install/lb.py
if test -x /etc/init.d/sufferage-lb && rc-service sufferage-lb status >/dev/null 2>&1; then
    rc-service sufferage-lb stop
fi
for item in /opt/sufferage-lb/lb.py /etc/init.d/sufferage-lb /usr/local/sbin/run-sufferage-lb; do
    if test -f "$item"; then cp -p "$item" "$item.before-install"; fi
done
cp /root/sufferage-lb-install/lb.py /opt/sufferage-lb/lb.py
chmod 0644 /opt/sufferage-lb/lb.py
cp /root/sufferage-lb-install/sufferage-lb /etc/init.d/sufferage-lb
chmod 0755 /etc/init.d/sufferage-lb
cp /root/sufferage-lb-install/run-sufferage-lb /usr/local/sbin/run-sufferage-lb
chmod 0755 /usr/local/sbin/run-sufferage-lb
rc-update add sufferage-lb default
rc-service sufferage-lb start
rc-service sufferage-lb status
'''))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 60
        last_error = ''
        while time.monotonic() < deadline:
            try:
                with opener.open('http://' + args.host + '/__lb/health', timeout=5) as response:
                    health = json.load(response)
                if health['algorithm'] == 'sufferage':
                    print(json.dumps(health, indent=2))
                    return
            except Exception as exc:
                last_error = str(exc)
            time.sleep(1)
        raise RuntimeError('LB HTTP readiness failed: ' + last_error)
    finally:
        client.close()


if __name__ == '__main__':
    main()
