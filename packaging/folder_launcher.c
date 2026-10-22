#define UNICODE
#define _UNICODE
#include <windows.h>
#include <stdio.h>
#include <wchar.h>
int wmain(void) {
    wchar_t root[32768], python[32768], command[65536];
    DWORD n = GetModuleFileNameW(NULL, root, 32768);
    if (!n || n >= 32768) return 1;
    wchar_t *last = wcsrchr(root, L'\\');
    if (!last) return 1;
    *last = 0;
    if (swprintf(python, 32768, L"%ls\\runtime\\python.exe", root) < 0 ||
        swprintf(command, 65536, L"\"%ls\" -I \"%ls\\run_server.py\"", python, root) < 0) return 1;
    STARTUPINFOW si = {0}; si.cb = sizeof(si);
    PROCESS_INFORMATION pi = {0};
    SetConsoleTitleW(L"Ship lightship regression - close with Ctrl+C");
    if (!CreateProcessW(python, command, NULL, NULL, FALSE, 0, NULL, root, &si, &pi)) {
        fwprintf(stderr, L"Launch failed (%lu). Extract the ENTIRE ZIP before starting.\n", GetLastError());
        MessageBoxW(NULL, L"Cannot start bundled Python. Extract the entire ZIP and keep the runtime folder beside this EXE.", L"Ship Regression", MB_OK|MB_ICONERROR);
        return 1;
    }
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 1; GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    if (code) {
        fwprintf(stderr, L"Program ended with error %lu. Press Enter to close.\n", code);
        getchar();
    }
    return (int)code;
}
