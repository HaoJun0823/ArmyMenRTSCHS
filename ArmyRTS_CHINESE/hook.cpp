// hook.cpp -- x86 inline hooks. Trampoline variant can still call the original.
#include "pch.h"
#include "hook.h"

bool PatchBytes(void* addr, const BYTE* data, size_t n) {
    if (!addr || !data || !n) return false;
    DWORD oldProt = 0;
    if (!VirtualProtect(addr, n, PAGE_EXECUTE_READWRITE, &oldProt)) return false;
    memcpy(addr, data, n);
    DWORD dummy = 0;
    VirtualProtect(addr, n, oldProt, &dummy);
    FlushInstructionCache(GetCurrentProcess(), addr, n);
    return true;
}

// ---- plain hook ----
bool HookInstall(Hook& h, void* target, void* detour) {
    if (!target || !detour) return false;
    h.target = target;
    memcpy(h.orig, target, 5);
    DWORD rel = (DWORD)((BYTE*)detour - ((BYTE*)target + 5));
    h.patch[0] = 0xE9;
    memcpy(&h.patch[1], &rel, 4);
    if (!PatchBytes(target, h.patch, 5)) return false;
    h.installed = true;
    return true;
}

bool HookRemove(Hook& h) {
    if (!h.installed || !h.target) return false;
    if (!PatchBytes(h.target, h.orig, 5)) return false;
    h.installed = false;
    return true;
}

// ---- instruction length decoder -------------------------------------------
//
// The earlier implementation enumerated opcode special cases ("8B 35", "8B 86",
// ...). That can never be complete: `mov ebp, esp` is `8B EC`, an ordinary
// modRM form that was not listed, so the walk refused and the draw hook at
// 0x4A2C50 was never installed. Without it, CJK text falls through to the
// engine's own single-byte lookup, GBK lead/trail bytes hit the Cyrillic slots
// 0xC0-0xFF the stock fonts contain, and the screen fills with Cyrillic.
//
// This decoder handles the general x86 forms that matter for hook prologues:
// prefixes, one/two-byte opcodes, modRM (with SIB and disp8/disp32) and
// immediates. Anything it cannot classify returns 0 and the hook refuses.

// Size of the modRM (plus optional SIB / displacement) starting at p[0].
// Returns 0 when truncated.
static int ModRMLen(const BYTE* p, int avail) {
    if (avail < 1) return 0;
    BYTE modrm = p[0];
    int mod = (modrm >> 6) & 3;
    int rm  = modrm & 7;

    int len = 1;                       // the modRM byte itself

    if (mod == 3) return len;          // register direct: no SIB, no disp

    if (rm == 4) {                     // SIB byte follows
        if (avail < 2) return 0;
        BYTE sib = p[1];
        len += 1;
        if (mod == 0 && (sib & 7) == 5) len += 4;   // disp32, no base
    } else if (mod == 0 && rm == 5) {
        len += 4;                      // disp32
    }
    if (mod == 1) len += 1;            // disp8
    else if (mod == 2) len += 4;       // disp32

    return (len <= avail) ? len : 0;
}

// Opcodes whose encoding is "opcode modRM [immediate]".
static bool HasModRM(BYTE op) {
    if (op <= 0x3F) return true;                 // ALU / test / xchg group
    if (op >= 0x80 && op <= 0x8F) return true;   // 80/81/83 group, test/xchg/
                                                // lea/mov/pop r/m
    if (op == 0xC0 || op == 0xC1) return true;   // shift group, imm8
    if (op == 0xC6 || op == 0xC7) return true;   // mov r/m, imm
    if (op >= 0xD0 && op <= 0xD3) return true;   // shift group by 1 / cl
    if (op >= 0xD8 && op <= 0xDF) return true;   // x87
    if (op >= 0xF6 && op <= 0xFF) return true;   // test/not/neg/mul/div, inc/dec,
                                                // call/jmp/push r/m
    return false;
}

// Immediate bytes after the modRM for the opcodes in HasModRM's range.
// 0x82 is an alias of 0x80 (imm8 sign-extended).
static int ImmBytes(BYTE op) {
    if (op == 0x69) return 4;
    if (op == 0x6B) return 1;
    if (op == 0x80 || op == 0x82 || op == 0x83) return 1;
    if (op == 0x81) return 4;
    if (op == 0xC0 || op == 0xC1) return 1;
    if (op == 0xC6) return 1;
    if (op == 0xC7) return 4;
    if (op == 0xF6) return 0;                    // reg field selects test imm;
                                                // conservative: no imm
    if (op == 0xF7) return 0;
    return 0;
}

static int DecodeInsnLen(const BYTE* p, int avail) {
    int i = 0;

    // prefixes (skip; each is its own byte)
    while (i < avail) {
        BYTE b = p[i];
        if (b == 0x26 || b == 0x2E || b == 0x36 || b == 0x3E ||
            b == 0x64 || b == 0x65 || b == 0x66 || b == 0x67 ||
            b == 0xF0 || b == 0xF2 || b == 0xF3) { ++i; continue; }
        break;
    }
    if (i >= avail) return 0;

    BYTE op = p[i++];

    // ---- two-byte opcode space ----
    if (op == 0x0F) {
        if (i >= avail) return 0;
        BYTE op2 = p[i++];
        if ((op2 & 0xF0) == 0x80) return i + 4;      // jcc rel32
        if (op2 == 0xB6 || op2 == 0xB7 || op2 == 0xBE || op2 == 0xBF ||
            op2 == 0xAF || op2 == 0xB0 || op2 == 0xB1) {
            int m = ModRMLen(p + i, avail - i);      // movzx/movsx/imul
            if (m <= 0) return 0;
            return i + m;
        }
        return 0;                                    // unhandled 0F form
    }

    // ---- relative branches / pushes ----
    if (op == 0xE8 || op == 0xE9) return i + 4;      // call/jmp rel32
    if (op == 0xEB || op == 0xE3) return i + 1;      // jmp/jecxz rel8
    if (op == 0x68) return i + 4;                    // push imm32
    if (op == 0x6A) return i + 1;                    // push imm8
    if (op == 0x69 || op == 0x6B) {                  // imul r, r/m, imm
        int m = ModRMLen(p + i, avail - i);
        if (m <= 0) return 0;
        return i + m + (op == 0x69 ? 4 : 1);
    }

    // ---- mov r, imm ----
    if (op >= 0xB0 && op <= 0xB7) return i + 1;
    if (op >= 0xB8 && op <= 0xBF) return i + 4;
    if (op == 0xA1 || op == 0xA3) return i + 4;      // moffs32 forms

    // ---- returns ----
    if (op == 0xC2) return i + 2;                    // ret imm16
    if (op == 0xC3) return i;                        // ret
    if (op == 0xCB) return i;                        // retf

    // ---- generic "op modRM [imm]" ----
    if (HasModRM(op)) {
        int m = ModRMLen(p + i, avail - i);
        if (m <= 0) return 0;
        return i + m + ImmBytes(op);
    }

    // ---- plain single-byte instructions ----
    if (op >= 0x50 && op <= 0x5F) return i;          // push/pop r32
    if (op == 0x90 || op == 0x98 || op == 0x99) return i;   // nop/cwde/cdq
    if (op == 0x9C || op == 0x9D) return i;          // pushfd/popfd
    if (op == 0xF4) return i;                        // hlt
    if (op == 0xF5) return i;                        // cmc
    if (op == 0xF8 || op == 0xF9 || op == 0xFC || op == 0xFD) return i;  // clc/stc/cld/std

    return 0;
}

bool HookInstallTrampoline(TrampolineHook& h, void* target, void* detour, int copyLen) {
    if (!target || !detour || copyLen < 5 || copyLen > 31) return false;

    const BYTE* t = (const BYTE*)target;

    // --- walk to a whole-instruction boundary >= copyLen ---
    // Round UP to the first boundary at or past copyLen. A boundary short of
    // copyLen is unusable: the JMP patch always covers 5 bytes, so copying
    // fewer bytes would leave part of the original first instruction behind the
    // detour and execute it as garbage.
    int i = 0;
    int realCopy = 0;
    while (i < 31) {
        int n = DecodeInsnLen(t + i, 31 - i);
        if (n <= 0) return false;      // undecodable: refuse rather than guess
        i += n;
        if (i >= copyLen) { realCopy = i; break; }
    }
    if (realCopy < copyLen) return false;

    h.copyLen = realCopy;
    memcpy(h.orig, target, realCopy);

    BYTE* stub = (BYTE*)VirtualAlloc(nullptr, 64, MEM_COMMIT | MEM_RESERVE,
                                     PAGE_EXECUTE_READWRITE);
    if (!stub) return false;

    memcpy(stub, target, realCopy);

    // Rewrite rip-relative displacements now that the bytes live at `stub`.
    // Original anchor = target + offset_of_displacement_field; new anchor is the
    // same offset within the stub. Walking with the real decoder (rather than
    // scanning every byte for 0xE8/0xE9) matters: a displacement byte inside an
    // immediate or a modRM disp32 can itself be 0xE8, and rewriting it would
    // corrupt an innocent instruction.
    {
        int k = 0;
        while (k < realCopy) {
            int n = DecodeInsnLen(t + k, realCopy - k);
            if (n <= 0) break;              // undecodable: leave the rest alone
            BYTE op = t[k];
            if (op == 0xE8 || op == 0xE9) {
                int rel = *(int*)(t + k + 1);
                DWORD oldTarget = (DWORD)((BYTE*)target + k + 5 + rel);
                DWORD newRel = oldTarget - (DWORD)(stub + k + 5);
                memcpy(stub + k + 1, &newRel, 4);
            } else if (op == 0x0F && n >= 6 && (t[k + 1] & 0xF0) == 0x80) {
                int rel = *(int*)(t + k + 2);
                DWORD oldTarget = (DWORD)((BYTE*)target + k + 6 + rel);
                DWORD newRel = oldTarget - (DWORD)(stub + k + 6);
                memcpy(stub + k + 2, &newRel, 4);
            }
            k += n;
        }
    }

    BYTE* jmpAt = stub + realCopy;
    DWORD rel = (DWORD)(((BYTE*)target + realCopy) - (jmpAt + 5));
    jmpAt[0] = 0xE9;
    memcpy(jmpAt + 1, &rel, 4);

    h.stub = stub;

    DWORD r2 = (DWORD)((BYTE*)detour - ((BYTE*)target + 5));
    BYTE patch[5];
    patch[0] = 0xE9;
    memcpy(patch + 1, &r2, 4);
    if (!PatchBytes(target, patch, 5)) {
        VirtualFree(stub, 0, MEM_RELEASE);
        h.stub = nullptr;
        return false;
    }
    FlushInstructionCache(GetCurrentProcess(), stub, realCopy + 5);
    h.installed = true;
    return true;
}

bool HookRemoveTrampoline(TrampolineHook& h) {
    if (!h.installed || !h.target) return false;
    if (!PatchBytes(h.target, h.orig, 5)) return false;
    if (h.stub) { VirtualFree(h.stub, 0, MEM_RELEASE); h.stub = nullptr; }
    h.installed = false;
    return true;
}
