// dllmain.cpp -- Army Men RTS in-process CJK patch (Plan B: English bitmap intact,
// CJK glyphs rasterized from TTF at runtime).
//
// Stage 1 (this file): font core + self-test + exports. Hook injection comes next.
// ASCII-only source on purpose: MSVC reads sources as codepage 936 and corrupts
// non-ASCII bytes in comments (C4819).

#include "pch.h"
#include "chs_core.h"
#include "chs_hook.h"
#include "chs_draw.h"
#include "chs_atlas.h"
#include <stdio.h>

ChsFont        g_font;
ChsAtlas       g_atlas;
bool           g_ready = false;
static HMODULE g_hModule = nullptr;
char           g_iniPath[MAX_PATH] = { 0 };
static char    g_logPath[MAX_PATH] = { 0 };

void Log(const char* fmt, ...) {
    FILE* f = fopen(g_logPath, "a");
    if (!f) return;
    va_list ap; va_start(ap, fmt);
    vfprintf(f, fmt, ap);
    va_end(ap);
    fprintf(f, "\n");
    fclose(f);
}

static struct {
    wchar_t fontPath[MAX_PATH];
    int     fontSize;
} g_cfg;

static void LoadConfig() {
    char dir[MAX_PATH] = { 0 };
    // Prefer the real DLL handle (saved at attach); fall back to NULL => exe path.
    GetModuleFileNameA(g_hModule ? g_hModule : nullptr, dir, MAX_PATH);
    char* slash = strrchr(dir, '\\');
    if (slash) *(slash + 1) = 0;

    strcpy_s(g_logPath, dir);
    strcat_s(g_logPath, "chs_debug.log");

    char cfg[MAX_PATH];
    strcpy_s(cfg, dir);
    strcat_s(cfg, "chs_config.ini");
    strcpy_s(g_iniPath, cfg);

    wcscpy_s(g_cfg.fontPath, L"C:\\Windows\\Fonts\\msyh.ttc");
    g_cfg.fontSize = 14;

    char buf[MAX_PATH] = { 0 };
    if (GetPrivateProfileStringA("Font", "Path", "", buf, MAX_PATH, cfg) > 0) {
        int n = MultiByteToWideChar(CP_UTF8, 0, buf, -1, g_cfg.fontPath, MAX_PATH);
        if (n <= 0) MultiByteToWideChar(936, 0, buf, -1, g_cfg.fontPath, MAX_PATH);
    }
    g_cfg.fontSize = GetPrivateProfileIntA("Font", "Size", 14, cfg);

    Log("=== chs asi init ===");
    Log("fontSize=%d", g_cfg.fontSize);
}

static bool SelfTest() {
    const wchar_t samples[] = { L'\x4E2D', L'\x6587', L'A' }; // CJK + ASCII
    for (wchar_t c : samples) {
        const Glyph* g = g_font.Get(c);
        if (!g) { Log("selftest FAIL for U+%04X", (unsigned)c); return false; }
        Log("U+%04X w=%d h=%d adv=%d by=%d bytes=%d",
            (unsigned)c, g->w, g->h, g->advance, g->bearingY, (int)g->alpha.size());
    }
    return true;
}

// Install every hook exactly once, whichever entry runs first.
// UAL loads the ASI via LoadLibrary -> DllMain always fires, then may call
// InitializeASI. Both paths funnel here so nothing depends on entry order.
static bool g_hooksDone = false;

static void InstallAllHooks(const char* via) {
    if (g_hooksDone) { Log("InstallAllHooks: already done (via %s)", via); return; }
    if (!g_ready) { Log("InstallAllHooks: skipped, font not ready (via %s)", via); return; }
    g_hooksDone = true;

    void* base = (void*)GetModuleHandleA(nullptr);
    Log("InstallAllHooks via %s: base=%p", via, base);

    // NOTE: the CJK atlas is loaded lazily on the first draw call, not here.
    // sub_4A26F0 allocates a 128x128 texture, which requires the render device
    // to be initialised; DllMain/InitializeASI both run far too early for that.

    int n = ChsInstallHooks(base);
    Log("  metric hooks=%d", n);
    int d = ChsDrawInstallHooks(base);
    Log("  draw hooks=%d", d);

    // The engine frees every texture when it reloads fonts (on entering the 3D
    // world), which invalidates our glyph texture ids. Observe that path so the
    // atlas can be rebuilt against the new numbering.
    ChsInstallTextureResetHook();
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID) {
    switch (reason) {
    case DLL_PROCESS_ATTACH:
        DisableThreadLibraryCalls(hModule);
        g_hModule = hModule;
        LoadConfig();
        if (g_font.Init(g_cfg.fontPath, g_cfg.fontSize)) {
            g_ready = SelfTest();
            Log("font init %s", g_ready ? "OK" : "FAILED");
        } else {
            Log("font init FAILED (Init false)");
        }
        InstallAllHooks("DllMain");
        break;
    case DLL_PROCESS_DETACH:
        ChsRemoveTextureResetHook();
        ChsDrawRemoveHooks();
        ChsRemoveHooks();
        g_font.Shutdown();
        break;
    default:
        break;
    }
    return TRUE;
}

extern "C" __declspec(dllexport)
int __stdcall ChsGetGlyph(wchar_t ch, int* w, int* h, int* adv, int* by, BYTE* buf, int bufSize) {
    if (!g_ready) return 0;
    const Glyph* g = g_font.Get(ch);
    if (!g) return 0;
    if (w)   *w = g->w;
    if (h)   *h = g->h;
    if (adv) *adv = g->advance;
    if (by)  *by = g->bearingY;
    if (buf && g->alpha.size() <= (size_t)bufSize)
        memcpy(buf, g->alpha.data(), g->alpha.size());
    return (int)g->alpha.size();
}

extern "C" __declspec(dllexport)
int __stdcall ChsIsReady() { return g_ready ? 1 : 0; }

extern "C" __declspec(dllexport)
int __stdcall ChsDecodeGbk(const BYTE* p, wchar_t* outCh) {
    wchar_t c = 0;
    int n = GBK_Decode(p, c);
    if (outCh) *outCh = c;
    return n;
}

extern "C" __declspec(dllexport)
int __stdcall ChsIsCjkByte(const BYTE* p) { return GBK_IsCjk(p) ? 1 : 0; }

// Ultimate ASI Loader entry point: called after the plugin is mapped.
// Exported so the loader recognizes this ASI even when DllMain attach order
// differs from plain LoadLibrary.
extern "C" __declspec(dllexport)
void __stdcall InitializeASI() {
    if (g_iniPath[0] == 0) LoadConfig();   // ensure config loaded

    // Prefer the real game module for hook base (not the loader).
    void* base = (void*)GetModuleHandleA(nullptr);
    Log("InitializeASI: base=%p ready=%d", base, (int)g_ready);

    if (!g_ready) {
        if (!g_font.Init(g_cfg.fontPath, g_cfg.fontSize)) {
            Log("InitializeASI: font init failed");
            return;
        }
        g_ready = SelfTest();
        Log("InitializeASI: font init %s", g_ready ? "OK" : "FAILED");
    }
    if (g_ready) {
        InstallAllHooks("InitializeASI");
    } else {
        Log("InitializeASI: font not ready");
    }
}
