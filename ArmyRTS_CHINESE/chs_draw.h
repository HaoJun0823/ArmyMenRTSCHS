// chs_draw.h -- Plan B draw hook: intercept text drawing for CJK.
// ASCII-only source (MSVC reads sources as codepage 936).
#pragma once
#include "hook.h"

int  ChsDrawInstallHooks(void* gameBase);
void ChsDrawRemoveHooks();

// Build the CJK atlas on first use. Shared by the draw and measure hooks so both
// use identical glyph advances (mismatched advances made long text drift).
void ChsEnsureAtlas();

// Discard the current atlas so the next use rebuilds it. Required after the
// engine destroys all textures (see ChsAtlasInvalidate below).
void ChsAtlasInvalidate();
void ChsInstallTextureResetHook();
void ChsRemoveTextureResetHook();

// Re-implementation of the engine glyph lookup sub_4A25E0(font, u8 ch):
//   count = *(u16*)(font + ch*8 + 0x11C)
//   array = *(u8**)(font + ch*8 + 0x120), entries 40 bytes, match *(u16*)e == ch
BYTE* ChsInlineGlyphLookup(void* font, unsigned char ch);
