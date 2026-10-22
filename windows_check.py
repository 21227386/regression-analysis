"""Run on the target Windows PC using the bundled Python runtime."""
import contextlib
import datetime
import io
import os
from pathlib import Path
import platform
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main():
    report = io.StringIO()
    report.write('Ship Regression validation\n')
    report.write(f'UTC: {datetime.datetime.now(datetime.timezone.utc).isoformat()}\n')
    report.write(f'Platform: {platform.platform()}\nPython: {sys.version}\n')
    report.write('Speed input: cruise speed (kn)\n')
    if sys.platform == 'win32':
        import ctypes
        try:
            wine_version = ctypes.WinDLL('ntdll').wine_get_version
        except AttributeError:
            report.write('Execution context: native Windows API (Wine export not detected)\n')
        else:
            wine_version.restype = ctypes.c_char_p
            report.write(f'Execution context: Wine {wine_version().decode()} compatibility layer; NOT a native Windows PC test\n')
    if sys.platform != 'win32':
        report.write('This validation entry point requires Windows.\n')
        print(report.getvalue())
        return 2
    os.chdir(ROOT)
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    with contextlib.redirect_stdout(report), contextlib.redirect_stderr(report):
        result = unittest.TextTestRunner(stream=report, verbosity=2).run(suite)
    report.write(f'\nResult: {"PASS" if result.wasSuccessful() else "FAIL"}\n')
    output = ROOT.parent / 'windows-validation.txt'
    try:
        output.write_text(report.getvalue(), encoding='utf-8-sig')
        print(f'Report: {output}')
    except OSError as exc:
        print(f'Cannot save report: {exc}')
    print(report.getvalue())
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    raise SystemExit(main())
