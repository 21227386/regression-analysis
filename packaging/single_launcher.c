#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <stdio.h>
#include <wchar.h>
#include <string.h>
#include "miniz.h"

#define CAP 32768
static FILE *logfile;
static const wchar_t *stage=L"Initialization";
static wchar_t logpath[CAP];
static DWORD failure_code;
static void note(const char *text) {
    puts(text); fflush(stdout);
    if (logfile) { fprintf(logfile,"%s\n",text); fflush(logfile); }
}
static void note_wide(const wchar_t *text) {
    int n=WideCharToMultiByte(CP_UTF8,0,text,-1,NULL,0,NULL,NULL);
    if (n<=0) return;
    char *utf8=malloc((size_t)n);
    if (utf8) { WideCharToMultiByte(CP_UTF8,0,text,-1,utf8,n,NULL,NULL); note(utf8); free(utf8); }
}
static int directory(wchar_t *path) {
    if (CreateDirectoryW(path,NULL)) return 1;
    if (GetLastError()==ERROR_ALREADY_EXISTS) {
        DWORD a=GetFileAttributesW(path);
        return a!=INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY);
    }
    return 0;
}
static int parents(wchar_t *path) {
    wchar_t *start=path+3;
    if (!wcsncmp(path,L"\\\\?\\UNC\\",8)) {
        start=wcschr(path+8,L'\\');
        if (!start || !(start=wcschr(start+1,L'\\'))) return 0;
        ++start;
    } else if (!wcsncmp(path,L"\\\\?\\",4)) start=path+7;
    for (wchar_t *p=start; *p; ++p) {
        if (*p==L'\\') {
            *p=0; int ok=directory(path); *p=L'\\';
            if (!ok) return 0;
        }
    }
    return 1;
}
static int file_exists(wchar_t *p) {
    DWORD a=GetFileAttributesW(p);
    return a!=INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}
static int join(wchar_t *dest,const wchar_t *base,const wchar_t *leaf) {
    return swprintf(dest,CAP,L"%ls\\%ls",base,leaf)>=0;
}
static DWORD run(wchar_t *app,wchar_t *command,wchar_t *dir) {
    STARTUPINFOW si={0}; PROCESS_INFORMATION pi={0}; si.cb=sizeof(si);
    if (!CreateProcessW(app,command,NULL,NULL,FALSE,0,NULL,dir,&si,&pi)) {
        failure_code=GetLastError(); return (DWORD)-1;
    }
    WaitForSingleObject(pi.hProcess,INFINITE);
    DWORD code=1; GetExitCodeProcess(pi.hProcess,&code);
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    return code;
}
typedef struct { HANDLE handle; mz_uint64 offset,size; } ArchiveInput;
static size_t archive_read(void *opaque,mz_uint64 offset,void *buffer,size_t size) {
    ArchiveInput *input=opaque; LARGE_INTEGER at; DWORD read=0;
    if (offset>input->size || size>input->size-offset || size>MAXDWORD) return 0;
    at.QuadPart=input->offset+offset;
    if (!SetFilePointerEx(input->handle,at,NULL,FILE_BEGIN)) return 0;
    if (!ReadFile(input->handle,buffer,(DWORD)size,&read,NULL)) return 0;
    return read;
}
static size_t archive_write(void *opaque,mz_uint64 offset,const void *buffer,size_t size) {
    HANDLE output=*(HANDLE *)opaque; LARGE_INTEGER at; DWORD written=0;
    if (size>MAXDWORD) return 0;
    at.QuadPart=offset;
    if (!SetFilePointerEx(output,at,NULL,FILE_BEGIN)) return 0;
    if (!WriteFile(output,buffer,(DWORD)size,&written,NULL)) return 0;
    return written;
}
/* Only package-relative UTF-8 paths are accepted; never escape the application cache. */
static int safe_name(const char *name) {
    if (!*name || *name=='/' || *name=='\\' || strchr(name,':')) return 0;
    const char *part=name;
    for (const char *p=name;;p++) {
        if (*p=='/' || *p=='\\' || !*p) {
            size_t len=(size_t)(p-part);
            if ((len==1 && part[0]=='.') || (len==2 && part[0]=='.' && part[1]=='.')) return 0;
            if (!*p) break;
            part=p+1;
        }
    }
    return 1;
}
static int unpack(HANDLE self,mz_uint64 offset,mz_uint64 size,wchar_t *dest) {
    ArchiveInput input={self,offset,size}; mz_zip_archive zip={0};
    zip.m_pRead=archive_read; zip.m_pIO_opaque=&input;
    if (!mz_zip_reader_init(&zip,size,0)) { note("Invalid embedded ZIP directory."); return 0; }
    mz_uint count=mz_zip_reader_get_num_files(&zip), last=101;
    int success=0;
    for (mz_uint index=0; index<count; ++index) {
        mz_zip_archive_file_stat info;
        char name[8192]; wchar_t relative[CAP], path[CAP], normal[CAP];
        mz_uint required=mz_zip_reader_get_filename(&zip,index,name,sizeof(name));
        if (!required || required>sizeof(name) || !safe_name(name)) { note("Unsafe or invalid package filename."); goto done; }
        if (!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,name,-1,relative,CAP)) goto done;
        for (wchar_t *p=relative; *p; ++p) if (*p==L'/') *p=L'\\';
        if (!join(normal,dest,relative)) goto done;
        if (!wcsncmp(normal,L"\\\\",2)) {
            if (swprintf(path,CAP,L"\\\\?\\UNC\\%ls",normal+2)<0) goto done;
        } else if (swprintf(path,CAP,L"\\\\?\\%ls",normal)<0) goto done;
        if (!mz_zip_reader_file_stat(&zip,index,&info)) goto done;
        if (mz_zip_reader_is_file_a_directory(&zip,index)) {
            size_t len=wcslen(path); if (len && path[len-1]==L'\\') path[len-1]=0;
            if (!parents(path) || !directory(path)) goto done;
            continue;
        }
        if (!parents(path)) goto done;
        HANDLE output=CreateFileW(path,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
        if (output==INVALID_HANDLE_VALUE) {
            failure_code=GetLastError();
            note("Cannot write file:"); note_wide(path);
            goto done;
        }
        int ok=mz_zip_reader_extract_to_callback(&zip,index,archive_write,&output,0);
        if (!ok) failure_code=GetLastError();
        CloseHandle(output);
        if (!ok) {
            note(mz_zip_get_error_string(mz_zip_get_last_error(&zip)));
            goto done;
        }
        mz_uint percent=count ? (index+1)*100/count : 100;
        if (percent/10!=last/10) {
            char message[120]; snprintf(message,sizeof(message),"Preparing files: %u%% (%u/%u)",percent,index+1,count);
            note(message); last=percent;
        }
    }
    note("Preparing files: 100% - integrity checks passed."); success=1;
done:
    mz_zip_reader_end(&zip); return success;
}
int wmain(void) {
    static wchar_t self[CAP],parent[CAP],appdir[CAP],cache[CAP],marker[CAP],runtime[CAP],script[CAP],command[CAP*2],message[CAP*2];
    HANDLE input=INVALID_HANDLE_VALUE, lock=NULL;
    int owns_lock=0; DWORD exit_code=1;
    SetConsoleOutputCP(CP_UTF8);
    SetConsoleTitleW(L"Naval Ship Weight Estimator");
    DWORD len=GetModuleFileNameW(NULL,self,CAP);
    if (!len || len>=CAP) goto fail;
    len=GetEnvironmentVariableW(L"LOCALAPPDATA",parent,CAP);
    if (!len || len>=CAP) { if (!GetTempPathW(CAP,parent)) goto fail; }
    if (!join(appdir,parent,L"NavalShipWeightEstimator") || !directory(appdir)) goto fail;
    if (!join(cache,appdir,L"CruiseNot_v2") || !directory(cache)) goto fail;
    if (!join(logpath,cache,L"startup.log")) goto fail;
    logfile=_wfopen(logpath,L"a");
    note("Naval Ship Weight Estimator - Windows launcher v2");
    note("Uses built-in extraction. PowerShell is not required.");
    note("Executable:"); note_wide(self); note("Cache:"); note_wide(cache);
    if (!join(marker,cache,L"ready.txt") || !join(runtime,cache,L"ShipRegression\\runtime\\python.exe") || !join(script,cache,L"ShipRegression\\run_server.py")) goto fail;
    stage=L"Waiting for another startup";
    lock=CreateMutexW(NULL,FALSE,L"Local\\NavalShipWeightEstimatorCruiseNotV2");
    if (!lock) goto fail;
    DWORD wait=WaitForSingleObject(lock,0);
    if (wait==WAIT_TIMEOUT) { note("Another instance is preparing files. Waiting..."); wait=WaitForSingleObject(lock,INFINITE); }
    if (wait!=WAIT_OBJECT_0 && wait!=WAIT_ABANDONED) goto fail;
    owns_lock=1;
    if (!file_exists(marker) || !file_exists(runtime) || !file_exists(script)) {
        stage=L"Checking embedded package";
        input=CreateFileW(self,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
        if (input==INVALID_HANDLE_VALUE) goto fail;
        LARGE_INTEGER size,pos; ULONGLONG payload=0; DWORD read=0; char magic[8];
        if (!GetFileSizeEx(input,&size) || size.QuadPart<16) goto fail;
        pos.QuadPart=-16;
        if (!SetFilePointerEx(input,pos,NULL,FILE_END)) goto fail;
        if (!ReadFile(input,&payload,8,&read,NULL) || read!=8) goto fail;
        if (!ReadFile(input,magic,8,&read,NULL) || read!=8 || memcmp(magic,"SHIPZIP1",8)) { note("Package is damaged or incomplete. Download the EXE again."); goto fail; }
        if (!payload || payload>(ULONGLONG)(size.QuadPart-16)) goto fail;
        ULARGE_INTEGER available;
        if (GetDiskFreeSpaceExW(cache,&available,NULL,NULL) && available.QuadPart<512ULL*1024*1024) {
            note("Not enough free space. At least 512 MB is required."); goto fail;
        }
        stage=L"Extracting application files";
        note("Preparing application files using built-in extractor...");
        if (!unpack(input,size.QuadPart-16-payload,payload,cache)) goto fail;
        CloseHandle(input); input=INVALID_HANDLE_VALUE;
        if (!file_exists(runtime) || !file_exists(script)) goto fail;
        HANDLE ready=CreateFileW(marker,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);
        if (ready==INVALID_HANDLE_VALUE) goto fail;
        DWORD written=0;
        int ok=WriteFile(ready,"v2\r\n",4,&written,NULL) && written==4;
        CloseHandle(ready); if (!ok) goto fail;
    } else note("Application files are ready (cached).");
    ReleaseMutex(lock); owns_lock=0; CloseHandle(lock); lock=NULL;
    stage=L"Starting Python application";
    if (swprintf(command,CAP*2,L"\"%ls\" -u -I \"%ls\"",runtime,script)<0) goto fail;
    note("Starting application. Keep this window open. Press Ctrl+C to stop.");
    exit_code=run(runtime,command,cache);
    if (exit_code) goto fail;
    if (logfile) fclose(logfile);
    return 0;
fail:
    if (!failure_code) failure_code=GetLastError();
    if (input!=INVALID_HANDLE_VALUE) CloseHandle(input);
    if (lock) { if (owns_lock) ReleaseMutex(lock); CloseHandle(lock); }
    swprintf(message,CAP*2,L"Unable to start Naval Ship Weight Estimator.\nStage: %ls\nWindows error: %lu\nApplication exit code: %lu\n\nDiagnostic folder:\n%ls\n\nPlease send startup.log and runtime.log from this folder for diagnosis.",stage,failure_code,exit_code,cache);
    fwprintf(stderr,L"%ls\n",message);
    note_wide(message); if (logfile) fclose(logfile);
    MessageBoxW(NULL,message,L"Naval Ship Weight Estimator - Startup error",MB_OK|MB_ICONERROR);
    return 1;
}
