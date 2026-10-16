// hook.h -- x86 inline hooks (plain 5-byte JMP, and JMP with trampoline).
// ASCII-only source (MSVC reads sources as codepage 936).
#pragma once
#include <windows.h>

// Plain hook: overwrite first 5 bytes with JMP. Caller must NOT call the
// original address afterwards (it now points at the detour) unless a
// trampoline is used.
struct Hook {
    void* target = nullptr;
    BYTE  orig[5] = { 0 };
    BYTE  patch[5] = { 0 };
    bool  installed = false;
};

// Hook that can still invoke the original function: copies `copyLen` whole
// instructions into an executable stub, then JMPs to target+copyLen.
// `stub` is the callable "original" (same ABI as the target).
struct TrampolineHook {
    void* target = nullptr;
    void* stub = nullptr;      // executable trampoline (call me to run original)
    int   copyLen = 0;
    BYTE  orig[32] = { 0 };
    bool  installed = false;
};

bool HookInstall(Hook& h, void* target, void* detour);
bool HookRemove(Hook& h);

bool HookInstallTrampoline(TrampolineHook& h, void* target, void* detour, int copyLen);
bool HookRemoveTrampoline(TrampolineHook& h);

bool PatchBytes(void* addr, const BYTE* data, size_t n);
