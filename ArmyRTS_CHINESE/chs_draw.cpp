// chs_draw.cpp -- Plan B draw hook: CJK glyphs resolved from private font pages.
//
// Target (IDA, Steam amrts.exe md5 a28b3085346fdfe483b0395bdf9bad5f):
//   sub_4A2C50  int __thiscall (Font* this, int x, int y, char* str, uint len,
//                               float color, int* clip, float alpha)  ret 0x1C
//   loop: g = sub_4A25E0(this, str[i]);  x += g->advance(u16 @+2);  UV = g+24..39
//   prologue 9 bytes: 55 8B EC 81 EC AC 00 00 00
//
// Strategy for CJK:
//   The engine lookup takes a BYTE, so we keep our own pages where CJK glyphs
//   are renumbered into slots 1..N. When the hook meets a GBK double-byte CJK
//   char, it runs the ENGINE path against OUR font table with that slot, so the
//   whole vertex/texture/UV pipeline stays engine-native.
//
// ASCII-only source (MSVC reads sources as codepage 936).

#include "pch.h"
#include "chs_draw.h"
#include "chs_core.h"
#include "chs_atlas.h"

extern ChsFont  g_font;
extern bool     g_ready;
extern ChsAtlas g_atlas;
void Log(const char* fmt, ...);
extern char g_iniPath[MAX_PATH];

static DWORD          g_addrDraw = 0x4A2C50;
static TrampolineHook g_drawHook = {};
static volatile LONG  g_inDraw = 0;
static int            g_cjkLogged = 0;
static int            g_diagBudget = 60;  // log the first N glyph decisions
static int            g_offX = 0;         // [Atlas] OffsetX, px
static int            g_offY = 0;         // [Atlas] OffsetY, px
static bool           g_offRead = false;

// Optional constant nudge for CJK glyphs. Advances are already unified with the
// measure hook, so this only corrects a fixed bias (e.g. the TTF's side bearing
// differing from the engine's expectation) -- it must NOT grow with text length.
static void ReadOffsets() {
    if (g_offRead) return;
    g_offRead = true;
    g_offX = GetPrivateProfileIntA("Atlas", "OffsetX", 0, g_iniPath);
    g_offY = GetPrivateProfileIntA("Atlas", "OffsetY", 0, g_iniPath);
    Log("draw: cjk offset = (%d, %d)", g_offX, g_offY);
}

// Diagnostic: dump every glyph decision for the first few draw calls, including
// misses, so a missing character can be traced to lookup vs. draw vs. atlas.
static void DiagGlyph(const char* stage, wchar_t ch, int slot, int page, void* g) {
    if (g_diagBudget <= 0) return;
    --g_diagBudget;
    Log("  [%s] U+%04X slot=%d page=%d glyph=%p adv=%u tex=%u",
        stage, (unsigned)ch, slot, page, g,
        g ? *(unsigned short*)((BYTE*)g + 2) : 0,
        g ? *(unsigned short*)((BYTE*)g + 4) : 0);
}

// Lazily build CJK font pages. Called from BOTH hooks: the measure hook may run
// before any draw, and it needs the same advances the draw path will use.
// The render device must exist, which is true by the time text is measured or
// drawn, but not in DllMain.
static volatile LONG g_atlasState = 0;   // 0=idle, 1=ok, 2=failed, 3=in progress

// Drop the atlas after the engine destroys its textures. The next draw/measure
// rebuilds it, and because rebuild happens lazily (not inside the engine's own
// reload loop) the new pages get correct, current texture ids.
void ChsAtlasInvalidate() {
    if (g_atlasState == 0) return;      // never built; nothing to drop
    g_atlas.Shutdown();
    InterlockedExchange(&g_atlasState, 0);
}

void ChsEnsureAtlas() {
    if (g_atlasState != 0) return;
    if (InterlockedCompareExchange(&g_atlasState, 3, 0) != 0) return;

    char dir[MAX_PATH];
    strcpy_s(dir, g_iniPath);
    char* slash = strrchr(dir, '\\');
    if (slash) *(slash + 1) = 0;

    char leaf[64] = { 0 };
    GetPrivateProfileStringA("Atlas", "Index", "chs_index.bin", leaf, 64, g_iniPath);

    char idx[MAX_PATH];
    _snprintf_s(idx, sizeof(idx), _TRUNCATE, "%s%s", dir, leaf);

    bool ok = g_atlas.Init(idx);
    Log("atlas: lazy init -> %s (%d groups, %d pages)",
        ok ? "OK" : "FAILED", g_atlas.GroupCount(), g_atlas.TotalPages());
    InterlockedExchange(&g_atlasState, ok ? 1 : 2);
}

// int __thiscall sub_4A2C50(Font*, int x, int y, char* str, uint len,
//                            float color, int* clip, float alpha) ; ret 0x1C
// x86 __fastcall: ECX=this, EDX=dummy, then 7 stack args.
typedef int(__fastcall* DrawFn)(void* this_, int edx, int x, int y,
                                const char* str, unsigned len, float color,
                                int* clip, float alpha);
static DrawFn g_origDraw = nullptr;

BYTE* ChsInlineGlyphLookup(void* font, unsigned char ch) {
    if (!font) return nullptr;
    BYTE* b = (BYTE*)font;
    unsigned short cnt = *(unsigned short*)(b + (size_t)ch * 8 + 0x11C);
    if (!cnt) return nullptr;
    BYTE* arr = *(BYTE**)(b + (size_t)ch * 8 + 0x120);
    if (!arr) return nullptr;
    for (unsigned short i = 0; i < cnt; ++i) {
        BYTE* e = arr + (size_t)i * 40;
        if (*(unsigned short*)e == (unsigned short)ch) return e;
    }
    return nullptr;
}

static int __fastcall DrawHook(void* f, int, int x, int y, const char* str,
                               unsigned len, float color, int* clip, float alpha) {
    if (!str || (int)len <= 0 || !g_origDraw) return (int)len;
    if (IsBadReadPtr(f, 0x920)) return (int)len;
    if (InterlockedExchange(&g_inDraw, 1) != 0) return (int)len;

    ChsEnsureAtlas();   // shared with the measure hook; safe to call first
    ReadOffsets();

    int i = 0;
    while (i < (int)len) {
        const BYTE* p = (const BYTE*)str + i;
        if (p[0] == 0) break;

        wchar_t ch = 0;
        int used = GBK_Decode(p, ch);

        if (used <= 0) {
            // Not a valid GBK sequence. NEVER hand the byte to the engine: its
            // u8 lookup maps 0x81..0xFE onto the stock fonts' Cyrillic slots.
            // Advance by a slot width so layout stays sane and keep walking.
            x += g_atlas.GroupCount() > 0 ? 7 : 6;
            i += 1;
            continue;
        }

        if (used == 2 && g_atlas.GroupCount() > 0) {
            // CJK: pick the size group matching the engine font in use, then draw
            // through the engine with our renumbered slot. Group is inferred from
            // the font's metric, so HUD / menu / cineractive all get right sizes.
            //
            // Note: no `ch >= 0x4E00` filter. GBK also carries punctuation
            // (U+3002, U+201C, U+00B7 ...) that sits below U+4E00; filtering on
            // the code point sent those to the engine's single-byte path, where
            // they rendered as two garbage characters.
            int page = -1;
            int slot = g_atlas.SlotOfFor(f, ch, &page);
            int gi = g_atlas.GroupFor(f);
            if (slot > 0) {
                void* table = g_atlas.TableOf(gi, page);
                BYTE* g = table ? ChsInlineGlyphLookup(table, (unsigned char)slot) : nullptr;

                if (g_cjkLogged < 20) {
                    Log("  cjk U+%04X group=%d slot=%d page=%d glyph=%p adv=%u tex=%u",
                        (unsigned)ch, gi, slot, page, g,
                        g ? *(unsigned short*)(g + 2) : 0,
                        g ? *(unsigned short*)(g + 4) : 0);
                    ++g_cjkLogged;
                }
                if (g) {
                    // Draw this one glyph through the engine. Its record carries
                    // UV into OUR page texture, so no custom rendering needed.
                    // Apply the optional constant nudge (TTF side bearing vs the
                    // engine's expectation); advances are already in sync with the
                    // measure hook, so this must stay constant, not per-character.
                    g_origDraw(table, 0, x + g_offX, y + g_offY,
                               (const char*)&slot, 1, color, clip, alpha);
                    x += *(unsigned short*)(g + 2);
                } else {
                    x += g_font.Height();
                }
            } else {
                // Decoded but not in our atlas: draw the raw pair so the engine
                // still shows something sensible instead of dropping it.
                g_origDraw(f, 0, x, y, (const char*)p, 2, color, clip, alpha);
                x += g_font.Height();
            }
        } else {
            g_origDraw(f, 0, x, y, (const char*)p, (unsigned)used, color, clip, alpha);
            BYTE* e = ChsInlineGlyphLookup(f, p[0]);
            x += e ? *(unsigned short*)(e + 2) : 6;
        }
        i += used;
    }

    InterlockedExchange(&g_inDraw, 0);
    return (int)len;
}

int ChsDrawInstallHooks(void* gameBase) {
    (void)gameBase;

    char buf[64] = { 0 };
    if (GetPrivateProfileStringA("Hook", "Draw", "", buf, 64, g_iniPath) > 0)
        g_addrDraw = strtoul(buf, nullptr, 0);

    void* target = (void*)(DWORD_PTR)g_addrDraw;

    static const BYTE expect[9] = { 0x55, 0x8B, 0xEC, 0x81, 0xEC, 0xAC, 0x00, 0x00, 0x00 };
    BYTE cur[9];
    memcpy(cur, target, 9);
    if (memcmp(cur, expect, 9) != 0) {
        Log("draw: REFUSE prologue mismatch @%p (%02X %02X %02X %02X %02X ...)",
            target, cur[0], cur[1], cur[2], cur[3], cur[4]);
        return 0;
    }

    if (!HookInstallTrampoline(g_drawHook, target, (void*)&DrawHook, 9)) {
        Log("draw: HookInstallTrampoline failed @%p", target);
        return 0;
    }
    g_origDraw = (DrawFn)g_drawHook.stub;
    Log("draw: hooked @%p stub=%p", target, g_drawHook.stub);
    return 1;
}

void ChsDrawRemoveHooks() {
    if (g_drawHook.installed) {
        HookRemoveTrampoline(g_drawHook);
        g_origDraw = nullptr;
        Log("draw: hooks removed");
    }
}

// ---- texture-lifetime hook -------------------------------------------------
//
// The engine frees EVERY texture in sub_4A5A30():
//     for (i = 0; i < 1000; ++i) if (dword_72778C[i]) { dword_72778C[i]->vtable[4](1); dword_72778C[i] = 0; }
//     dword_727788 = 0;
// It has TWO callers:
//     sub_4A5AF0  -- reloads every registered font afterwards
//     sub_4A5940  -- does NOT reload fonts (just tears down lists)
// Entering the 3D world takes the sub_4A5940 route, so hooking only
// sub_4A5AF0 (the earlier attempt) never fired and the atlas kept stale
// texture ids -> glyphs sampled foreign textures -> solid blocks.
//
// Hooking sub_4A5A30 itself covers both callers. Its prologue is
//   56 57 BE <imm32> BF <imm32> 8B 0E 85 C9
// (push esi; push edi; mov esi, imm32; mov edi, imm32; mov ecx,[esi]; test ecx,ecx)
// -- boundaries 0/1/2/8/14/16, and no rel32 that needs relocating.
//
// We only observe (drop the atlas); the trampoline still runs the original.
typedef int(__cdecl* ResetFontsFn)();
static ResetFontsFn  g_origResetFonts = nullptr;
static TrampolineHook g_hookResetFonts;
static DWORD         g_addrResetFonts = 0x4A5A30;

static int __cdecl ResetFontsHook() {
    // Drop BEFORE the original runs: the engine is about to free every texture,
    // so any record pointing at them is already stale.
    ChsAtlasInvalidate();
    int r = g_origResetFonts ? g_origResetFonts() : 0;
    Log("texreset: engine freed all textures; atlas dropped (rebuild on next draw)");
    return r;
}

void ChsInstallTextureResetHook() {
    char buf[64] = { 0 };
    if (GetPrivateProfileStringA("Hook", "ResetFonts", "", buf, 64, g_iniPath) > 0)
        g_addrResetFonts = strtoul(buf, nullptr, 0);

    void* target = (void*)(DWORD_PTR)g_addrResetFonts;
    // Real prologue (verified via IDA on the unpatched image):
    //   56                 push esi
    //   57                 push edi
    //   BE 8C 77 72 00     mov  esi, 0x72778C
    //   BF E8 03 00 00     mov  edi, 0x3E8
    //   8B 0E              mov  ecx, [esi]
    //   85 C9              test ecx, ecx
    // Boundaries: 0/1/2/8/14/16. Requesting 11 rounds up to 14. Neither `mov
    // r, imm32` carries a rel32, so no displacement rewriting is needed.
    static const BYTE expect[7] = { 0x56, 0x57, 0xBE, 0x8C, 0x77, 0x72, 0x00 };
    BYTE cur[7];
    memcpy(cur, target, 7);
    if (memcmp(cur, expect, 7) != 0) {
        Log("texreset: REFUSE prologue mismatch @%p (%02X %02X %02X %02X %02X %02X %02X)",
            target, cur[0], cur[1], cur[2], cur[3], cur[4], cur[5], cur[6]);
        return;
    }

    if (!HookInstallTrampoline(g_hookResetFonts, target, (void*)&ResetFontsHook, 11)) {
        Log("texreset: hook failed @%p (no instruction boundary at/past 11 bytes)",
            target);
        return;
    }
    g_origResetFonts = (ResetFontsFn)g_hookResetFonts.stub;
    Log("texreset: hooked @%p stub=%p", target, g_hookResetFonts.stub);
}

void ChsRemoveTextureResetHook() {
    if (g_hookResetFonts.installed) {
        HookRemoveTrampoline(g_hookResetFonts);
        g_origResetFonts = nullptr;
        Log("texreset: hook removed");
    }
}
