// chs_hook.cpp -- Plan B: CJK text metrics hook.
//
// FIX HISTORY (root cause of the infinite loop, confirmed in x32dbg):
//   v1 hooked BOTH 0x4A25E0 (glyph lookup) and 0x4A2650 (measure), and the
//   detours called "g_origXxx" which pointed at the ALREADY-PATCHED address
//   (first 5 bytes = E9 <rel>). So the detour jumped back into itself ->
//   unbounded recursion -> hang. Also sub_4A2650 is __thiscall (ECX=this),
//   but it was declared __stdcall, dropping `this`.
//
// v2 (this file): correctness first, safety second.
//   * hook ONLY the measure routine 0x4A2650
//   * NEVER call a patched address: glyph lookup is re-implemented inline
//     as plain memory reads (no calls, no recursion possible)
//   * detour signature __fastcall(this, unused, str, len) == __thiscall ABI
//     (ECX=this, str at [esp+4], len at [esp+8], callee-cleanup)
//   * verify original prologue bytes before patching; refuse if mismatch
//   * re-entry guard as a belt-and-braces safety net
//
// ASCII-only source: MSVC reads sources as codepage 936, so non-ASCII bytes
// in comments corrupt token boundaries (C4819 + bogus "undeclared identifier").

#include "pch.h"
#include "chs_hook.h"
#include "chs_core.h"
#include "chs_atlas.h"
#include "chs_draw.h"    // ChsEnsureAtlas
#include <stdio.h>

extern ChsFont  g_font;
extern ChsAtlas g_atlas;
extern bool     g_ready;
void Log(const char* fmt, ...);

extern char g_iniPath[MAX_PATH];

// ---- target ----
static DWORD g_addrMeasure = 0x4A2650;   // int __thiscall (Font*, char*, int)
static Hook  g_hookMeasure;

// Expected original prologue of sub_4A2650 (from unpatched amrts.exe):
//   push ebp ; mov ebp, esp ; push ecx ; push esi
static const BYTE EXPECT_MEASURE[5] = { 0x55, 0x8B, 0xEC, 0x51, 0x56 };

// ---- inline re-implementation of sub_4A25E0(Font* this, u8 ch) ----
// Disasm: mov di,[ecx+eax*8+11Ch]   ; candidate count (u16), eax = ch & 0xFF
//         mov v4, [ecx+eax*8+120h]  ; glyph array pointer
//         scan entries (stride 40), match *(u16*)entry == ch
// Returns pointer to the 40-byte glyph entry, or 0.
static BYTE* InlineLookup(void* font, unsigned char ch) {
    if (!font) return nullptr;
    BYTE* base = (BYTE*)font;
    unsigned short cnt = *(unsigned short*)(base + (size_t)ch * 8 + 0x11C);
    if (!cnt) return nullptr;
    BYTE* arr = *(BYTE**)(base + (size_t)ch * 8 + 0x120);
    if (!arr) return nullptr;
    for (unsigned short i = 0; i < cnt; ++i) {
        BYTE* e = arr + (size_t)i * 40;
        if (*(unsigned short*)e == (unsigned short)ch) return e;
    }
    return nullptr;
}

// ---- re-entry guard ----
static volatile LONG g_inHook = 0;

// ---- detour ----
// __fastcall(this_, edx_unused, str, len): ECX=this, str at [esp+4], len at [esp+8].
// This is ABI-identical to __thiscall sub_4A2650(Font*, const char*, int).
static int __fastcall MeasureHook(void* this_, int /*edx_unused*/,
                                  const char* str, int len) {
    if (InterlockedExchange(&g_inHook, 1) != 0) {
        // Should never happen: reentry means something is wrong; use len*7
        // as a conservative non-recursive fallback.
        return len > 0 ? len * 7 : 0;
    }

    int total = 0;
    if (str && len > 0) {
        ChsEnsureAtlas();   // need the atlas to read the same advances as draw
        int i = 0;
        while (i < len) {
            const BYTE* p = (const BYTE*)str + i;
            if (p[0] == 0) break;

            wchar_t ch = 0;
            int used = GBK_Decode(p, ch);

            if (used <= 0) {
                // Invalid GBK byte. Skip it; never let it reach the engine's u8
                // lookup (0x81..0xFE maps to the stock fonts' Cyrillic slots).
                // Must advance by the same amount the draw hook uses.
                total += 7;
                i += 1;
                continue;
            }

            if (used == 2 && g_atlas.GroupCount() > 0) {
                // CJK: one glyph for two bytes. Use the SAME advance the draw
                // hook uses (the .fff entry's u16). Measuring with a different
                // value than drawing makes the engine compute a start x from one
                // advance while the glyphs advance by another, so the error grows
                // with each character -- measured text drifted increasingly left.
                int adv = 0;
                adv = g_atlas.GlyphAdvanceOf(this_, ch);
                if (adv <= 0) {
                    const Glyph* g = g_ready ? g_font.Get(ch) : nullptr;
                    adv = g ? g->advance : (g_font.Height() > 0 ? g_font.Height() : 14);
                }
                total += adv;
            } else {
                // ASCII / single byte: replicate engine advance via inline lookup.
                BYTE* e = InlineLookup(this_, (unsigned char)p[0]);
                total += e ? *(unsigned short*)(e + 2) : 6;
            }
            i += used;
        }
    }

    InterlockedExchange(&g_inHook, 0);
    return total;
}

int ChsInstallHooks(void* gameBase) {
    (void)gameBase;
    Log("install hooks (v2: measure-only)");

    char buf[64] = { 0 };
    if (GetPrivateProfileStringA("Hook", "Measure", "", buf, 64, g_iniPath) > 0)
        g_addrMeasure = strtoul(buf, nullptr, 0);

    void* target = (void*)(DWORD_PTR)g_addrMeasure;
    Log("  target measure = %p", target);

    // ---- safety: verify original prologue before patching ----
    BYTE cur[5];
    memcpy(cur, target, 5);
    if (memcmp(cur, EXPECT_MEASURE, 5) != 0) {
        Log("  REFUSE: prologue mismatch at %p", target);
        Log("    expected %02X %02X %02X %02X %02X",
            EXPECT_MEASURE[0], EXPECT_MEASURE[1], EXPECT_MEASURE[2],
            EXPECT_MEASURE[3], EXPECT_MEASURE[4]);
        Log("    actual   %02X %02X %02X %02X %02X",
            cur[0], cur[1], cur[2], cur[3], cur[4]);
        return 0;   // never patch a wrong address
    }

    int n = 0;
    if (HookInstall(g_hookMeasure, target, (void*)&MeasureHook)) {
        n++;
        Log("  hooked measure @%p -> %p", target, (void*)&MeasureHook);
    } else {
        Log("  FAIL HookInstall @%p", target);
    }
    Log("hooks installed=%d", n);
    return n;
}

void ChsRemoveHooks() {
    if (g_hookMeasure.installed) HookRemove(g_hookMeasure);
    Log("hooks removed");
}
