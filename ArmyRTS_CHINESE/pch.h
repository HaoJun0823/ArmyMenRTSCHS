// pch.h: precompiled header.
// Kept ASCII-only (MSVC reads sources as codepage 936; non-ASCII bytes in
// comments trigger C4819 and can corrupt token boundaries).
#ifndef PCH_H
#define PCH_H

#ifndef _CRT_SECURE_NO_WARNINGS
#define _CRT_SECURE_NO_WARNINGS
#endif

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <stdlib.h>

#include "framework.h"

#endif // PCH_H
