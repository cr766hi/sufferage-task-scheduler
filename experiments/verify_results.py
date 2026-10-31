import csv
import argparse
import json
import math
from pathlib import Path

parser = argparse.ArgumentParser(description='Verify complete client/proxy request logs and fault timing')
parser.add_argument('directory', type=Path)
directory = parser.parse_args().directory.resolve()
manifest = json.loads((directory / 'manifest.json').read_text())
total = 0
checked = 0
faults = []
snapshot_deltas = []
export_warnings = []
for run in manifest['runs']:
    if run['state'] != 'complete':
        continue
    name = run['name']
    with (directory / (name + '-client.csv')).open(newline='') as stream:
        client = list(csv.DictReader(stream))
    with (directory / (name + '-lb.csv')).open(newline='') as stream:
        proxy = list(csv.DictReader(stream))
    assert len(client) == len(proxy) == run['requests'], name
    client_ids = [r['request_id'] for r in client]
    proxy_ids = [r['request_id'] for r in proxy]
    assert len(set(client_ids)) == len(client_ids), name + ': duplicate client request ID'
    assert set(client_ids) == set(proxy_ids), name + ': missing proxy/client match'
    assert all(r['algoritma'] == run['algorithm'] for r in proxy), name
    assert all(math.isfinite(float(r['response_time_ms'])) and float(r['response_time_ms']) >= 0 for r in client), name
    errors = sum(bool(r['error']) or not 200 <= int(r['status']) < 400 for r in client)
    assert errors == run['errors'], name
    with (directory / (name + '_stats.csv')).open(newline='') as stream:
        aggregate = next(r for r in csv.DictReader(stream) if r['Name'] == 'Aggregated')
    snapshot_count = int(aggregate['Request Count'])
    assert snapshot_count <= len(client), name + ': snapshot exceeds actual request log'
    if snapshot_count != len(client):
        snapshot_deltas.append({'run': name, 'periodic_stats_count': snapshot_count,
                                'final_request_log_count': len(client)})
    assert int(aggregate['Failure Count']) == errors, name
    log = (directory / (name + '-locust.log')).read_text(encoding='utf-8')
    warning = 'ValueError: I/O operation on closed file.'
    if warning in log:
        assert 'Shape test completed' in log and log.index(warning) > log.index('Shape test completed'), name
        export_warnings.append({'run': name, 'error': warning, 'occurred_after_test_completion': True})
    if run['scenario'] == 'fault':
        start = json.loads((directory / (name + '-client.started.json')).read_text())['epoch']
        fault = run['fault']
        offset = fault['acknowledged_epoch'] - start
        assert 0 < offset < manifest['duration'], name + ': fault outside measurement'
        assert fault['healthy_epoch'] > fault['restore_command_epoch'] > fault['acknowledged_epoch'], name
        faults.append({'run': name, 'stop_ack_seconds_into_test': round(offset, 2),
                       'recovery_verification_seconds': round(fault['healthy_epoch'] - fault['restore_command_epoch'], 2),
                       'manual_reset_required': fault.get('recovery_required_manual_reset', False)})
    checked += 1
    total += len(client)
result = {'checked_runs': checked, 'requests_client_and_lb_matched': total,
          'unique_request_ids_within_runs': True, 'locust_failure_totals_match': True,
          'periodic_locust_snapshot_deltas': snapshot_deltas,
          'post_test_locust_csv_export_warnings': export_warnings,
          'faults_inside_measurement_window': faults}
if manifest['status'] == 'complete':
    assert checked == len(manifest['scenarios']) * manifest['repeats'] * 3
    (directory / 'verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
