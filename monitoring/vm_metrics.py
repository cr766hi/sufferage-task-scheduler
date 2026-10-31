"""Read guest-wide Linux resource counters, without psutil or blocking CPU probes."""
from datetime import datetime, timezone
from pathlib import Path
import time


def parse_cpu(stat):
    line = next(line for line in stat.splitlines() if line.startswith('cpu '))
    counters = [int(value) for value in line.split()[1:9]]
    counters += [0] * (8 - len(counters))
    # guest/guest_nice (fields 9/10) are already included in user/nice.
    user, nice, system, idle, iowait, irq, softirq, steal = counters
    return {'cpu_total_ticks': sum(counters),
            'cpu_busy_ticks': user + nice + system + irq + softirq,
            'cpu_iowait_ticks': iowait, 'cpu_steal_ticks': steal}


def parse_memory(meminfo):
    values = {line.split(':', 1)[0]: int(line.split()[1])
              for line in meminfo.splitlines() if ':' in line}
    total = values['MemTotal']
    available = min(total, max(0, values['MemAvailable']))
    if total <= 0:
        raise ValueError('MemTotal must be positive')
    used = total - available
    return {'ram_total_mb': round(total / 1024, 3),
            'ram_used_mb': round(used / 1024, 3),
            'ram_available_mb': round(available / 1024, 3),
            'ram_percent': round(100 * used / total, 3)}


def snapshot(vm, proc_root=Path('/proc')):
    proc_root = Path(proc_root)
    stat = (proc_root / 'stat').read_text()
    return {'vm': vm, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'sample_monotonic_seconds': time.monotonic(),
            'boot_id': (proc_root / 'sys/kernel/random/boot_id').read_text().strip(),
            'vcpus': sum(line.startswith('cpu') and line[3:4].isdigit()
                         for line in stat.splitlines()),
            **parse_cpu(stat), **parse_memory((proc_root / 'meminfo').read_text())}
