// chs_atlas.cpp -- load generated .fff pages into private engine font objects.
//
// Two engine facts shape this file:
//  1. Glyph lookup sub_4A25E0(Font*, u8 ch) indexes with a BYTE, so a Unicode
//     code point (0x4E2D) would be truncated. The generator renumbers CJK glyphs
//     into slots 1..N per page; we keep the Unicode -> (group, page, slot) map.
//  2. The game uses SEVERAL fonts with different row heights (metric):
//     arial_10 metric=16, stencil_14 metric=19, stencil_24 metric=30. Rendering
//     CJK at one size looks wrong somewhere, so we build one font-object set per
//     metric and pick by the metric of the font the engine is currently using.
//
// Each page is loaded by the ENGINE's own .fff loader, so texture creation,
// packing and UV math stay engine-native.
//
// ASCII-only source (MSVC reads sources as codepage 936).

#include "pch.h"
#include "chs_atlas.h"
#include <stdio.h>

void Log(const char* fmt, ...);

static FffLoadFn g_fffLoad = nullptr;

bool ChsAtlas::Init(const char* indexBinPath) {
    g_fffLoad = (FffLoadFn)(DWORD_PTR)ADDR_FFF_LOAD;

    // ---- index: "CHSI" | u32 count | u16 groupCount | u8 prefixLen | prefix ----
    FILE* f = fopen(indexBinPath, "rb");
    if (!f) { Log("atlas: cannot open index %s", indexBinPath); return false; }
    char magic[4];
    if (fread(magic, 1, 4, f) != 4 || memcmp(magic, "CHSI", 4) != 0) {
        fclose(f); Log("atlas: bad index magic"); return false;
    }
    unsigned int count = 0;
    unsigned short groupCount = 0;
    if (fread(&count, 4, 1, f) != 1 || fread(&groupCount, 2, 1, f) != 1) {
        fclose(f); Log("atlas: index header short"); return false;
    }
    if (count == 0 || groupCount == 0 || groupCount > 8) {
        fclose(f); Log("atlas: bad counts (%u glyphs, %u groups)", count, groupCount);
        return false;
    }

    unsigned char plen = 0;
    if (fread(&plen, 1, 1, f) != 1) { fclose(f); return false; }
    char prefix[128] = { 0 };
    if (plen > 0 && plen < sizeof(prefix)) {
        if (fread(prefix, 1, plen, f) != plen) { fclose(f); return false; }
        prefix[plen] = 0;
    }
    strncpy_s(prefix_, prefix[0] ? prefix : "library\\language\\", _TRUNCATE);

    // per-group: u16 metric, u16 pageCount
    struct GP { unsigned short metric, pages; };
    GP gp[8];
    for (unsigned short i = 0; i < groupCount; ++i) {
        if (fread(&gp[i].metric, 2, 1, f) != 1 || fread(&gp[i].pages, 2, 1, f) != 1) {
            fclose(f); Log("atlas: group header short"); return false;
        }
    }

    // glyph records: u32 uni, u16 group, u16 page, u16 slot, u8 adv, u8 pad = 12B
    struct Rec { unsigned int uni; unsigned short g, p, s; };
    Rec* recs = (Rec*)malloc(sizeof(Rec) * count);
    if (!recs) { fclose(f); return false; }
    unsigned int got = 0;
    for (unsigned int i = 0; i < count; ++i) {
        unsigned char b[12];
        if (fread(b, 1, 12, f) != 12) break;
        Rec r;
        memcpy(&r.uni, b, 4);
        memcpy(&r.g, b + 4, 2);
        memcpy(&r.p, b + 6, 2);
        memcpy(&r.s, b + 8, 2);
        recs[got++] = r;
    }
    fclose(f);

    // ---- allocate objects + load pages per group ----
    groupCount_ = groupCount;
    int totalPages = 0;
    for (unsigned short i = 0; i < groupCount; ++i) {
        ChsGroup& G = groups_[i];
        G.metric = gp[i].metric;
        G.pageCount = gp[i].pages;
        G.objs = (unsigned char*)malloc((size_t)FONT_OBJ_SIZE * G.pageCount);
        G.tables = (void**)malloc(sizeof(void*) * G.pageCount);
        if (!G.objs || !G.tables) { Log("atlas: alloc failed group %u", i); return false; }
        memset(G.objs, 0, (size_t)FONT_OBJ_SIZE * G.pageCount);
        memset(G.tables, 0, sizeof(void*) * G.pageCount);

        int loaded = 0;
        for (int p = 0; p < G.pageCount; ++p) {
            unsigned char* obj = G.objs + (size_t)p * FONT_OBJ_SIZE;
            void* table = obj + FONT_GLYPHTAB_OFF;
            char full[MAX_PATH];
            _snprintf_s(full, sizeof(full), _TRUNCATE, "%schs_g%d_p%02d.fff", prefix_, i, p);

            int r = 0;
            __try {
                r = g_fffLoad(table, 0, full);
            } __except (EXCEPTION_EXECUTE_HANDLER) {
                r = -1;
            }
            G.tables[p] = table;
            if (r > 0) ++loaded;
        }
        totalPages += G.pageCount;
        Log("atlas: group %u metric=%u pages=%d loaded=%d", i, G.metric, G.pageCount, loaded);
    }

    // ---- distribute glyph records into groups ----
    for (unsigned short i = 0; i < groupCount; ++i) {
        unsigned int n = 0;
        for (unsigned int k = 0; k < got; ++k) if (recs[k].g == i) ++n;
        groups_[i].map = (ChsGroup::Entry*)malloc(sizeof(ChsGroup::Entry) * (n ? n : 1));
        groups_[i].mapCount = 0;
        for (unsigned int k = 0; k < got; ++k) {
            if (recs[k].g != i) continue;
            ChsGroup::Entry e;
            e.uni = recs[k].uni; e.page = recs[k].p; e.slot = recs[k].s;
            groups_[i].map[groups_[i].mapCount++] = e;
        }
    }
    free(recs);

    Log("atlas: ready, %u groups, %u glyph records, %d pages", groupCount_, got, totalPages);
    return true;
}

void ChsAtlas::Shutdown() {
    for (int i = 0; i < groupCount_; ++i) {
        ChsGroup& G = groups_[i];
        if (G.map) { free(G.map); G.map = nullptr; }
        if (G.tables) { free(G.tables); G.tables = nullptr; }
        if (G.objs) { free(G.objs); G.objs = nullptr; }
    }
    groupCount_ = 0;
}

// Identify which group matches the engine font object. The engine passes the
// glyph-table pointer to its draw routine (the same pointer sub_4A25E0 uses),
// and metric lives at table + 0x114 as a single BYTE (sub_4A26F0 does
// "v67[69] = *v7" with v7 being unsigned __int8*, i.e. a byte store into a
// dword-sized slot). Read one byte only, so neighbouring bytes never leak in.
int ChsAtlas::GroupFor(void* table) const {
    if (!table) return -1;
    unsigned int metric = *((unsigned char*)table + FONT_METRIC_OFF);
    for (int i = 0; i < groupCount_; ++i) {
        if ((unsigned int)groups_[i].metric == metric) return i;
    }
    return -1;
}

int ChsAtlas::SlotOfFor(void* table, wchar_t ch, int* pageOut) const {
    int gi = GroupFor(table);
    if (gi < 0) { if (pageOut) *pageOut = -1; return 0; }
    const ChsGroup& G = groups_[gi];
    unsigned int u = (unsigned int)ch;
    for (unsigned int i = 0; i < G.mapCount; ++i) {
        if (G.map[i].uni == u) {
            if (pageOut) *pageOut = (int)G.map[i].page;
            return (int)G.map[i].slot;
        }
    }
    if (pageOut) *pageOut = -1;
    return 0;
}

void* ChsAtlas::TableOf(int group, int page) const {
    if (group < 0 || group >= groupCount_) return nullptr;
    const ChsGroup& G = groups_[group];
    if (!G.tables || page < 0 || page >= G.pageCount) return nullptr;
    return G.tables[page];
}

// Same lookup the draw hook uses (font + ch*8 + 0x11C / 0x120, 40-byte stride).
static BYTE* LookupInTable(void* table, unsigned char slot) {
    if (!table) return nullptr;
    BYTE* b = (BYTE*)table;
    unsigned short cnt = *(unsigned short*)(b + (size_t)slot * 8 + 0x11C);
    if (!cnt) return nullptr;
    BYTE* arr = *(BYTE**)(b + (size_t)slot * 8 + 0x120);
    if (!arr) return nullptr;
    for (unsigned short i = 0; i < cnt; ++i) {
        BYTE* e = arr + (size_t)i * 40;
        if (*(unsigned short*)e == (unsigned short)slot) return e;
    }
    return nullptr;
}

int ChsAtlas::GlyphAdvanceOf(void* table, wchar_t ch) const {
    int page = -1;
    int slot = SlotOfFor(table, ch, &page);
    if (slot <= 0) return 0;
    int gi = GroupFor(table);
    BYTE* g = LookupInTable(TableOf(gi, page), (unsigned char)slot);
    return g ? (int)*(unsigned short*)(g + 2) : 0;
}

int ChsAtlas::TotalPages() const {
    int n = 0;
    for (int i = 0; i < groupCount_; ++i) n += groups_[i].pageCount;
    return n;
}
