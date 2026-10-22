"""Bundled Windows entry point with a persistent startup diagnostic log."""
import os
from pathlib import Path
import socket
import sys
import threading
import time
import traceback
import urllib.request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'application'))


class Tee:
    def __init__(self, console, log):
        self.console, self.log = console, log

    def write(self, text):
        if self.console:
            self.console.write(text)
            self.console.flush()
        self.log.write(text)
        self.log.flush()
        return len(text)

    def flush(self):
        if self.console:
            self.console.flush()
        self.log.flush()

    def __getattr__(self, name):
        return getattr(self.console, name)


def main():
    port = None
    for candidate in range(8501, 8521):
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', candidate))
            except OSError:
                continue
            port = candidate
            break
    if port is None:
        raise RuntimeError('Ports 8501-8520 are unavailable. Close an earlier instance and retry.')
    url = f'http://127.0.0.1:{port}'
    print('Naval Ship Weight Estimator\nKeep this window open. Press Ctrl+C to stop.\n' + url, flush=True)

    def open_browser():
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(120):
            try:
                with opener.open(url + '/_stcore/health', timeout=1) as response:
                    if response.status == 200:
                        print('Application is ready. Open ' + url, flush=True)
                        if not os.environ.get('SHIP_REGRESSION_NO_BROWSER'):
                            try:
                                os.startfile(url)
                            except OSError:
                                print('Browser did not open automatically. Open ' + url + ' manually.', flush=True)
                                traceback.print_exc()
                        return
            except OSError:
                pass
            time.sleep(.5)
        print('Readiness check timed out. Check runtime.log for the startup error.', flush=True)

    threading.Thread(target=open_browser, daemon=True).start()
    from streamlit.web import cli
    sys.argv = ['streamlit', 'run', str(ROOT / 'application' / 'app.py'),
                '--server.address=127.0.0.1', f'--server.port={port}',
                '--server.headless=true', '--browser.gatherUsageStats=false',
                '--server.fileWatcherType=none']
    return cli.main()


def entry():
    logpath = ROOT.parent / 'runtime.log'
    with logpath.open('a', encoding='utf-8', buffering=1) as log:
        original_out, original_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = Tee(original_out, log), Tee(original_err, log)
        try:
            print('\nStarting Naval Ship Weight Estimator; Python ' + sys.version, flush=True)
            return main()
        except Exception:
            traceback.print_exc()
            return 1
        finally:
            sys.stdout, sys.stderr = original_out, original_err


if __name__ == '__main__':
    raise SystemExit(entry())
