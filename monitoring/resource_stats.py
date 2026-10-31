"""Shared resource sampling arithmetic for the batch scheduler."""
import statistics


def cpu_delta(previous, current):
    if not previous or previous['boot_id'] != current['boot_id']:
        return {}
    total = current['cpu_total_ticks'] - previous['cpu_total_ticks']
    busy = current['cpu_busy_ticks'] - previous['cpu_busy_ticks']
    seconds = current['sample_monotonic_seconds'] - previous['sample_monotonic_seconds']
    if total <= 0 or busy < 0 or busy > total or seconds <= 0:
        return {}
    return dict(cpu_percent=100 * busy / total, cpu_busy_delta_ticks=busy,
                cpu_total_delta_ticks=total, resource_interval_seconds=seconds)


def summarize_resources(samples):
    summaries = []
    for vm in sorted({sample['vm'] for sample in samples}):
        all_samples = [sample for sample in samples if sample['vm'] == vm]
        valid = [sample for sample in all_samples if sample['resource_status'] == 'ok']
        cpu = [sample for sample in valid if 'cpu_percent' in sample]
        total = sum(sample['cpu_total_delta_ticks'] for sample in cpu)
        summaries.append(dict(vm=vm, resource_ok_samples=len(valid),
            resource_error_samples=len(all_samples) - len(valid), cpu_valid_samples=len(cpu),
            resource_observed_seconds=sum(sample['resource_interval_seconds'] for sample in cpu),
            cpu_avg_percent=100 * sum(sample['cpu_busy_delta_ticks'] for sample in cpu) / total if total else None,
            cpu_peak_percent=max((sample['cpu_percent'] for sample in cpu), default=None),
            ram_avg_percent=statistics.mean(sample['ram_percent'] for sample in valid) if valid else None,
            ram_peak_percent=max((sample['ram_percent'] for sample in valid), default=None),
            ram_peak_used_mb=max((sample['ram_used_mb'] for sample in valid), default=None),
            ram_total_mb=valid[-1]['ram_total_mb'] if valid else None,
            vcpus=valid[-1].get('vcpus') if valid else None))
    return summaries
