// chs_hook.h -- Plan B: CJK text metrics hook (single hook, no trampoline).
// ASCII-only source (MSVC reads sources as codepage 936).
#pragma once
#include "hook.h"

// Installs the measurement hook using addresses from chs_config.ini.
// Returns number of hooks installed (0 or 1).
int  ChsInstallHooks(void* gameBase);
void ChsRemoveHooks();
