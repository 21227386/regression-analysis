#define UNICODE
#define _UNICODE
#include <windows.h>
#include <stdio.h>
#include <wchar.h>
#include <string.h>

static int run(wchar_t *app, wchar_t *command, wchar_t *dir, DWORD flags) {
    STARTUPINFOW si = {0}; PROCESS_INFORMATION pi = {0};
    si.cb = sizeof(si);
    if (!CreateProcessW(app,command,NULL,NULL,FALSE,flags,NULL,dir,&si,&pi)) return -1;
    WaitForSingleObject(pi.hProcess,INFINITE);
    DWORD code=1; GetExitCodeProcess(pi.hProcess,&code);
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    return (int)code;
}
static int exists(wchar_t *p) { return GetFileAttributesW(p)!=INVALID_FILE_ATTRIBUTES; }
int wmain(void) {
    wchar_t self[32768], parent[32768], cache[32768], zip[32768], marker[32768];
    wchar_t inner[32768], runtime[32768], powershell[32768], command[65536];
    HANDLE lock=NULL, input=INVALID_HANDLE_VALUE, output=INVALID_HANDLE_VALUE;
    int result=1; DWORD count=0;
    SetConsoleTitleW(L"Ship Regression - cruise speed (not)");
    if (!GetModuleFileNameW(NULL,self,32768)) goto fail;
    if (!GetEnvironmentVariableW(L"LOCALAPPDATA",parent,32768)) {
        if (!GetTempPathW(32768,parent)) goto fail;
    }
    if (swprintf(cache,32768,L"%ls\\ShipRegression",parent)<0) goto fail;
    CreateDirectoryW(cache,NULL);
    if (swprintf(cache,32768,L"%ls\\ShipRegression\\CruiseNot_20261022_v1",parent)<0) goto fail;
    CreateDirectoryW(cache,NULL);
    swprintf(zip,32768,L"%ls\\package.zip",cache);
    swprintf(marker,32768,L"%ls\\ready.txt",cache);
    swprintf(inner,32768,L"%ls\\ShipRegression\\ShipRegression.exe",cache);
    swprintf(runtime,32768,L"%ls\\ShipRegression\\runtime\\python.exe",cache);
    lock=CreateMutexW(NULL,FALSE,L"Local\\ShipRegressionCruiseNot20261022v1");
    if (!lock) goto fail;
    DWORD waited=WaitForSingleObject(lock,INFINITE);
    if (waited!=WAIT_OBJECT_0 && waited!=WAIT_ABANDONED) goto fail;
    if (!exists(marker) || !exists(inner) || !exists(runtime)) {
        puts("Preparing application files. Please wait..."); fflush(stdout);
        input=CreateFileW(self,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
        if (input==INVALID_HANDLE_VALUE) goto fail;
        LARGE_INTEGER size,pos; ULONGLONG payload=0; char magic[8];
        if (!GetFileSizeEx(input,&size) || size.QuadPart<16) goto fail;
        pos.QuadPart=-16;
        if (!SetFilePointerEx(input,pos,NULL,FILE_END)) goto fail;
        if (!ReadFile(input,&payload,8,&count,NULL) || count!=8) goto fail;
        if (!ReadFile(input,magic,8,&count,NULL) || count!=8 || memcmp(magic,"SHIPZIP1",8)) goto fail;
        if (!payload || payload>(ULONGLONG)(size.QuadPart-16)) goto fail;
        pos.QuadPart=size.QuadPart-16-payload;
        if (!SetFilePointerEx(input,pos,NULL,FILE_BEGIN)) goto fail;
        output=CreateFileW(zip,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);
        if (output==INVALID_HANDLE_VALUE) goto fail;
        char buffer[65536]; ULONGLONG remaining=payload;
        while (remaining) {
            DWORD want=remaining>sizeof(buffer)?sizeof(buffer):(DWORD)remaining;
            DWORD written=0;
            if (!ReadFile(input,buffer,want,&count,NULL) || count!=want) goto fail;
            if (!WriteFile(output,buffer,count,&written,NULL) || written!=count) goto fail;
            remaining-=count;
        }
        CloseHandle(output); output=INVALID_HANDLE_VALUE;
        CloseHandle(input); input=INVALID_HANDLE_VALUE;
        if (!GetSystemDirectoryW(powershell,32768)) goto fail;
        if (wcslen(powershell)+50>=32768) goto fail;
        wcscat(powershell,L"\\WindowsPowerShell\\v1.0\\powershell.exe");
        SetEnvironmentVariableW(L"SHIP_PACKAGE_ZIP",zip);
        SetEnvironmentVariableW(L"SHIP_PACKAGE_DIR",cache);
        swprintf(command,65536,L"\"%ls\" -NoLogo -NoProfile -NonInteractive -Command \"$ErrorActionPreference='Stop'; Expand-Archive -LiteralPath $env:SHIP_PACKAGE_ZIP -DestinationPath $env:SHIP_PACKAGE_DIR -Force\"",powershell);
        if (run(powershell,command,cache,CREATE_NO_WINDOW)!=0 || !exists(inner) || !exists(runtime)) goto fail;
        output=CreateFileW(marker,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);
        if (output==INVALID_HANDLE_VALUE) goto fail;
        const char *text="ShipRegression cruise speed display not; package v1\r\n";
        if (!WriteFile(output,text,(DWORD)strlen(text),&count,NULL)) goto fail;
        CloseHandle(output); output=INVALID_HANDLE_VALUE;
        DeleteFileW(zip);
    }
    ReleaseMutex(lock); CloseHandle(lock); lock=NULL;
    swprintf(command,65536,L"\"%ls\"",inner);
    puts("Starting application. Keep this window open; press Ctrl+C to stop."); fflush(stdout);
    result=run(inner,command,cache,0);
    if (result==0) return 0;
fail:
    if (input!=INVALID_HANDLE_VALUE) CloseHandle(input);
    if (output!=INVALID_HANDLE_VALUE) CloseHandle(output);
    if (lock) { ReleaseMutex(lock); CloseHandle(lock); }
    fwprintf(stderr,L"Unable to start application (Windows error %lu).\n",GetLastError());
    MessageBoxW(NULL,L"Unable to prepare or start the application. Check available disk space and Windows PowerShell availability. Keep the console error message for diagnosis.",L"Ship Regression",MB_OK|MB_ICONERROR);
    return 1;
}
