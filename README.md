# Army Men RTS 简体中文补丁

《玩具兵大战 RTS》（Army Men RTS）Steam 版的非官方简体中文汉化补丁。

运行时内存注入实现，**不修改 `amrts.exe`，一个字节都不改**。

- 适用版本：Steam 版 `amrts.exe`，md5 `a28b3085346fdfe483b0395bdf9bad5f`
- 注入方式：Ultimate ASI Loader（代理 `binkw32.dll`）加载 `scripts\ArmyRTS_CHINESE.asi`
- 逆向依据：IDA Pro 对 `amrts.exe` 的反编译（见下文"引擎地址表"）

---

## 安装

1. **先安装兼容性补丁**（必需，见下文"注意事项"）。
2. 关闭游戏。
3. 把本仓库的 `asi\`、`scripts\` 内容复制到游戏根目录，`update\` 复制到游戏目录。
   最终结构：

   ```
   <游戏目录>\
   ├─ binkw32.dll                     <- Ultimate ASI Loader（代理）
   ├─ binkw32Hooked.dll
   ├─ scripts\
   │   ├─ ArmyRTS_CHINESE.asi         <- 汉化插件（Release 构建产物）
   │   ├─ chs_config.ini
   │   └─ chs_index.bin               <- 汉字 -> 字库页/槽位索引
   └─ update\
       └─ library\
           └─ language\
               ├─ english.dat         <- 中文文本（DOCB 格式）
               └─ chs_g*_p*.fff       <- 87 页中文字库
   ```

4. 启动游戏。`scripts\chs_debug.log` 记录加载情况，用于排查问题。

### 注意事项（唯一一条）

**必须先安装社区兼容性补丁**，否则游戏在新系统上无法正常运行：

<https://community.pcgamingwiki.com/files/file/3215-army-men-rts-custom-patch/>

该补丁不是本项目的组成部分，需要单独下载安装。

---

## 做了什么

### 文本汉化

`library\language\english.dat` 采用 Pandemic 的 **DOCB** 二进制容器（非明文 ini）。
游戏按**路径段 CRC32** 查字符串，因此节点名（键）不可翻译，只翻译叶子值。

- 846 条字符串，其中 821 条已译为中文
- 25 条保留原文（纯占位符、纯数字、NATO 音标字母）
- `®` / `©` 改写为 `(R)` / `(C)`（GBK 无法编码）

工具链（[`Tools/dat_tool.py`](Tools/dat_tool.py)）：

```
unpack  english.dat -> json          保留 tag，字节级无损
export  json -> tsv                  导出待翻译表
apply   tsv -> json                  只替换叶子值，键与 tag 不动
pack    json -> dat                  重建并同步 header[0x30]
verify                               往返自检，应输出 IDENTICAL: True
```

格式依据来自 IDA 反编译 + 字节级往返校验（34334 字节完全一致）。
**注意**：1 代源码不含 DOCB 实现，格式并非来自源码。

### 中文字体

游戏引擎用点阵字体（`.fff`），字形查找 `sub_4A25E0` **只按 `u8` 索引**，
Unicode 码位会被截断。做法是把汉字重编号到槽位 1..N，由生成器打包成多页 `.fff`，
交给**引擎自己的加载器** `sub_4A26F0` 加载，纹理创建、打包、UV 计算全部保持引擎原生。

```
Tools/gen_fff.py    TTF -> 多尺寸多页 .fff + 索引
Tools/make_fff.py   .fff 解析 / 重建（4/4 原版字体往返一致）
```

三组字号对应三个原版字体，运行时按当前字体的 metric 自动选组：

| 组 | metric | 对应原版字体 | 用途 |
|---|---|---|---|
| g0 | 16 | `font_arial_10.fff` | System / Console / Button |
| g1 | 19 | `font_stencil_14.fff` | Debriefing |
| g2 | 30 | `font_stencil_24.fff` | Movie / Resource |

87 页由**模拟引擎打包算法**自动分页（每页 128×128），容量全部校验通过。

### 运行时 hook

只 hook 两个文字函数，其余（字形查表）改为内联内存读取，避免递归：

| 函数 | 作用 |
|---|---|
| `sub_4A2650` | 文本测宽 |
| `sub_4A2C50` | 文本绘制 |
| `sub_4A5A30` | 观察：引擎销毁全部纹理时丢弃 atlas 并重建 |

**测宽与绘制必须使用同一份 advance**（`.fff` 条目的 `u16`）。
两者不一致时，引擎按一个值算起始 x、按另一个值排字，误差逐字累积——表现为文本越长越偏。这个坑踩过。

---

## 从源码构建

工具链：MSVC v141（VS 2017 15.9）、Win10 SDK。

```
msbuild ArmyRTS_CHINESE\ArmyRTS_CHINESE.vcxproj /p:Configuration=Release /p:Platform=Win32
```

产物 `ArmyRTS_CHINESE\Release\ArmyRTS_CHINESE.dll` 重命名为 `.asi` 即为插件。

重新生成字库与文本：

```
python _build_full.py       # 字库 + 索引 + 中文 english.dat
python _deploy_full.py      # 部署到游戏目录（需先关闭游戏）
python _verify_full.py      # 全量校验
```

---

## 目录结构

```
ArmyRTS_CHINESE/    插件源码（C++，MSVC v141）
  chs_core.*        GDI + TTF 栅格化、GBK 解码
  chs_atlas.*       多组字库页管理、字形索引
  chs_hook.cpp      测宽 hook
  chs_draw.cpp      绘制 hook、纹理销毁观察
  hook.*            x86 inline hook（含指令边界解码 + rel32 重定位）

Tools/              解包打包 + 字库生成
translate/          翻译分区与合并结果
asi/                ASI Loader 代理 DLL
docs/               逆向工程技术发现
LICENSES/           第三方许可
```

以下目录**不在版本库内**（见 `.gitignore`），由脚本生成或属本地归档：

| 目录 | 内容 | 生成方式 |
|---|---|---|
| `build_full/` | 字库页 + 索引 + 中文 `english.dat` | `python _build_full.py` |
| `Resource_EN/` | 原版资源备份（104 文件） | 手工备份，属游戏资产 |
| `_trash/` | 废弃脚本与探查残留 | 归档，不参与构建 |

部署时 `build_full/` 是唯一来源，`_deploy_full.py` 直接从它取文件。

---

## 引擎地址表

Steam 版 `amrts.exe`，imagebase `0x400000`。**换 exe 版本需重新定位。**

| 地址 | 函数 |
|---|---|
| `0x4A26F0` | `.fff` 加载器 |
| `0x4A2540` | 字体对象初始化 |
| `0x4A25E0` | 字形查找（`u8` 索引） |
| `0x4A2650` | 文本测宽 |
| `0x4A2C50` | 文本绘制 |
| `0x4A5A30` | 销毁全部纹理 |
| `0x4A55A0` | 分配纹理页 ID |
| `0x4D94D0` | VFS 打开 |
| `0x4D9410` | 直接磁盘打开 |
| `0x4D8150` | 已注册文件系统链 |
| `0x4DB6E0` | block file 打开 |

---

## 已知限制

- 6 张社区多人地图的图内英文烧字未处理。
- 电影为原版画面，无中文字幕。
- 中文字库基于微软雅黑栅格化，与游戏原有美术风格不完全一致。

---

## 校对贡献与 PS2 移植参考

[木下萌子 / MoekoSama](https://github.com/MoekoSama) 提供了单位术语校对与 PS2 移植调查，使用 Codex 辅助实现、GPT-6 Luna 辅助校对。详见[本次修订与验证边界](docs/localization-review-2026-10-21.md)及[独立归档的 PS2 源码参考](ports/ps2/README.md)。PC 发布前需要根据新增“吉”字重新生成字体页和索引；本次没有修改 PC 插件或提交新二进制发布包。

## 许可

本汉化补丁：GPL-3.0-or-later（见 [LICENSE](LICENSE) 与 [LICENSES/GPLv3.txt](LICENSES/GPLv3.txt)）
Ultimate ASI Loader：MIT License, Copyright (c) 2023 ThirteenAG（见 [LICENSES/ASILoader.txt](LICENSES/ASILoader.txt)）

《Army Men RTS》(c) 2002 The 3DO Company. All rights reserved.
本项目为非官方粉丝汉化，与游戏版权方无任何关联。
