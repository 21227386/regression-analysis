"""Windowed entry point: native GUI, local diagnostic log, no browser/server."""
import ctypes
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'application'))


def main():
    logpath = ROOT.parent / 'runtime.log'
    original_out, original_err = sys.stdout, sys.stderr
    with logpath.open('a', encoding='utf-8', buffering=1) as log:
        sys.stdout = sys.stderr = log
        try:
            print('\nNaval Ship Weight Estimator — desktop GUI\nPython: ' + sys.version, flush=True)
            from desktop_app import main as run_gui
            return run_gui()
        except Exception:
            traceback.print_exc()
            ctypes.windll.user32.MessageBoxW(None,
                '프로그램을 시작할 수 없습니다. 진단 로그를 확인하세요.\n\n' + str(logpath),
                'Naval Ship Weight Estimator', 0x10)
            return 1
        finally:
            sys.stdout, sys.stderr = original_out, original_err


if __name__ == '__main__':
    raise SystemExit(main())
