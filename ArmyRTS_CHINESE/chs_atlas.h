// chs_atlas.h -- private font objects built from generated .fff pages
// ASCII-only source (MSVC reads sources as codepage 936).
#pragma once
#include <windows.h>

// Engine addresses (Steam amrts.exe md5 a28b3085346fdfe483b0395bdf9bad5f)
#define ADDR_FONT_INIT    0x4A2540   // void __thiscall sub_4A2540(Font* glyphTable)
#define ADDR_FFF_LOAD     0x4A26F0   // int  __thiscall sub_4A26F0(Font* glyphTable, const char* file)

// Font object layout (from sub_4A26F0 / sub_4A5690):
//   object+0     name (0x40 bytes)
//   object+68    hash
//   object+72    == the "table" pointer the engine uses at runtime
//   table+0x11C  glyph candidate counts, table+0x120 glyph arrays (u8 index)
//   table+0x114  metric (row height, u8) -- sub_4A26F0 does "v67[69] = *v7"
//                with v67 == table, and 69*4 == 0x114
// Total object allocation 0x97C (72 + 0x91C fits).
#define FONT_OBJ_SIZE     0x97C
#define FONT_GLYPHTAB_OFF 72
#define FONT_METRIC_OFF   0x114      // relative to TABLE, not to object base

typedef int(__fastcall* FffLoadFn)(void* table, int, const char* file);

// One size group = one metric + its own set of .fff pages / font objects.
struct ChsGroup {
    unsigned short metric = 0;
    int            pageCount = 0;
    unsigned char* objs = nullptr;      // pageCount * FONT_OBJ_SIZE
    void**         tables = nullptr;    // pageCount entries
    struct Entry { unsigned int uni; unsigned short page; unsigned short slot; };
    Entry*         map = nullptr;
    unsigned int   mapCount = 0;
};

class ChsAtlas {
public:
    bool Init(const char* indexBinPath);
    void Shutdown();

    // Pick the group whose metric matches the engine font object `table`
    // (the glyph-table pointer the engine passes to its draw routine).
    // Writes the owning page index; returns the slot (>0) or 0 if unmapped.
    int   SlotOfFor(void* table, wchar_t ch, int* pageOut) const;
    void* TableOf(int group, int page) const;
    int   GroupFor(void* table) const;
    int   GroupCount() const { return groupCount_; }
    int   TotalPages() const;

    // Advance (px) of a CJK glyph exactly as the DRAW path will use it, i.e.
    // the .fff entry's u16 at +2. Measuring must use this same value, otherwise
    // the engine computes a start x from one advance and lays out glyphs with
    // another, and the mismatch accumulates per character (longer text drifts
    // further). Returns 0 when the glyph is unknown.
    int   GlyphAdvanceOf(void* table, wchar_t ch) const;

private:
    ChsGroup groups_[8];
    int      groupCount_ = 0;
    char     prefix_[128] = { 0 };
};
