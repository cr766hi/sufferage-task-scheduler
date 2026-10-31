"""Clear numbered local test CSVs and rebuild an empty results page."""
import argparse
from pathlib import Path
import re
import urllib.error
import urllib.request
import json
from scheduler_report import generate_report


def check_scheduler(server):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(server.rstrip('/') + '/api/health', timeout=6) as response:
            health = json.load(response)
    except (urllib.error.URLError, TimeoutError) as error:
        print('Info: scheduler tidak terjangkau; pembersihan hanya berlaku pada hasil lokal.')
        return
    if health.get('role') != 'task_scheduler':
        raise RuntimeError('Respons server bukan task scheduler; pembersihan dibatalkan.')
    if health.get('active_batch'):
        raise RuntimeError('Batch masih aktif: ' + health['active_batch'] + '. Tunggu selesai terlebih dahulu.')


def clean_local_results(root, preview=False):
    root = Path(root).resolve()
    if not (root / 'datasets').is_dir() or not (root / 'vm210/sufferage.py').is_file():
        raise RuntimeError('Akar proyek tidak dikenali; pembersihan dibatalkan.')
    directory = root / 'results'
    if directory.is_symlink() or getattr(directory, 'is_junction', lambda: False)():
        raise RuntimeError('Folder results berupa link/junction; pembersihan dibatalkan.')
    if directory.resolve() != directory:
        raise RuntimeError('Folder hasil keluar dari lokasi proyek.')
    page = root / 'hasil_pengujian.html'
    if page.is_symlink():
        raise RuntimeError('Halaman HTML berupa link; pembersihan dibatalkan.')
    files = []
    for path in directory.iterdir() if directory.exists() else []:
        if not re.fullmatch(r'pengujian [1-9][0-9]*\.csv', path.name):
            continue
        if path.is_symlink() or not path.is_file() or path.resolve().parent != directory:
            raise RuntimeError('Target CSV tidak aman: ' + path.name)
        files.append(path)
    files.sort(key=lambda path: int(path.stem.split()[-1]))
    print('Folder hasil:', directory)
    print('CSV pengujian:', len(files))
    for path in files:
        print(' -', path.name)
    if preview:
        print('PREVIEW: belum ada file yang dihapus atau HTML yang diubah.')
        return len(files)
    # Check write access first; locked files still cause a clear error on unlink.
    for path in [*files, *([page] if page.exists() else [])]:
        with path.open('r+b'):
            pass
    removed = 0
    try:
        for path in files:
            path.unlink()
            removed += 1
    except OSError as error:
        raise RuntimeError(f'{removed} CSV sudah dihapus; file berikutnya terkunci/tidak dapat dihapus: {path.name}. Tutup Excel/aplikasi yang membukanya lalu ulangi. {error}') from error
    directory.mkdir(exist_ok=True)
    generate_report(root)
    print(f'Selesai: {removed} CSV dihapus dan HTML hasil dibuat ulang.')
    print('Pengujian baru mulai dari pengujian 1.csv. Refresh halaman HTML.')
    return removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--server', default='http://192.168.56.10')
    args = parser.parse_args()
    if not args.preview:
        check_scheduler(args.server)
    try:
        clean_local_results(Path(__file__).resolve().parents[1], args.preview)
    except PermissionError as error:
        raise SystemExit('File hasil masih terbuka atau akses ditolak. Tutup Excel/aplikasi yang membuka file lalu ulangi. ' + str(error))


if __name__ == '__main__':
    main()
