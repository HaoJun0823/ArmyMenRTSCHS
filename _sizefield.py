import sys, struct
sys.stdout.reconfigure(encoding='utf-8')

for p, lbl in [(r"I:\LocalGames\Army Men\Army Men RTS STEAM\library\language\english.dat", "ORIG"),
               (r"G:\Projects\ArmyMenRTSCHS\build_chs\english.dat", "PACK")]:
    d = open(p, "rb").read()
    top = struct.unpack_from("<H", d, 0x34)[0]
    size_field = struct.unpack_from("<I", d, 0x30)[0]
    calc = len(d) - 52 - 12
    print("%s: len=%d  0x30=%d  数据区(0x34..len-12)=%d  顶层数@0x34=%d  %s" %
          (lbl, len(d), size_field, calc, top, "OK" if size_field == calc else "MISMATCH"))
    print("    尾部: %s  (末4字节=%d)" % (d[-12:].hex(), struct.unpack_from("<I", d, len(d)-8)[0]))
