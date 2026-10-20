# PS2 中文移植源码参考与交接

目标：Army Men RTS USA / SLUS-20206。贡献：[木下萌子 / MoekoSama](https://github.com/MoekoSama)，Codex 辅助实现与分析，GPT-6 Luna 辅助术语校对。PC 中文语料来自本项目；原作者署名和仓库 GPL-3.0-or-later 许可保留。

## 文件清单

| 文件 | 用途 |
|---|---|
| `source/native_patch.py`、`native_strings.py` | R5900 指令组装、GBK 解码/查字/测宽/绘制/换行钩子、内存所有权修复及原生记忆卡消息。 |
| `source/test_native.py` | 执行实际组装指令的主机模型；检查对齐、边界、完整 128 位寄存器保存、测宽与断行。不是 PCSX2。 |
| `source/build_assets.py` | DOCB 文本重建、控制符检查及 BORK 字体补字参考。 |
| `source/build_disc.py`、`verify_disc.py` | NORK 字体别名、ISO 元数据、目录尺寸缓存、资源对齐和独立回读。 |
| `source/inventory.py`、`check_assets.py`、`check_layout.py` | 字体绑定盘点、缺字/纹理打包预算与可静态解析的布局检查。 |
| `source/tutorial-translations.json` | 19 条 PS2 教程措辞修订，另复核保留了其他教程目标。 |
| `source/unit-translations.json` | 5 条单位/建筑/人物称呼统一，PC 可用部分另同步到根目录语料。 |
| `source/inputs/menu-sample/work/` | 前期菜单样例的解析/栅格化辅助源码和已接受的菜单译文。 |
| `source/inputs/iso-evidence.json` | 原盘目录项的结构元数据，不含游戏文件内容。 |
| `source/revisions/v0.2.4/assets-validation.json` | 旧字体基线的尺寸/摘要元数据，不含字体位图。 |
| `source-provenance.json` | 导出前后源码摘要与路径替换说明。 |
| `validation-v0.2.5.json` | 原工程 v0.2.5 的历史静态检查摘要。 |

## 输入与可复现性限制

这些是原工程已使用实现的**源码参考快照**。仅将私人路径字面量换成 `inputs/` 下的占位路径，未宣称已经移植成可从本仓库一键构建的工具链。复现仍需要本人持有的匹配原盘、原版 ELF/DOCB/字体、PC 中文 DAT、v0.2.4 字体基线，以及供 `build_assets.py` 调用的 `inputs/check_font_coverage.py`（接口为 `font_coverage(path, face_index)`，返回 Unicode 码位集合、cmap 格式和字体信息）。这些二进制输入和外部字体检查工具不随提交提供。

参考布局（路径相对 `source/` 工作目录）：

```text
inputs/original.iso
inputs/source/ps2/SLUS_202.06.elf
inputs/source/ps2/ENGLISH.DAT
inputs/source/ps2/base_extract/<original .fff files>
inputs/source/chs_patch/update/library/language/english.dat
revisions/v0.2.4/fonts/<accepted Chinese .fff baselines>
inputs/check_font_coverage.py
```

Pillow、Windows 微软雅黑字体及匹配输入是原构建条件；不得把字体本体或原游戏文件补进 PR。生成的文件和模拟器资料应放在独立工作区，不能直接提交。

## 关键技术发现

- DOCB 的节点键、元数据与控制符必须保持；PS2 共 838 个叶子，PC 共 846 个。两个平台不能按记录数量直接互换。
- BORK 字体支持完整 `u16` 码位；原生 256 个低字节桶能继续按完整码位比较，记录跨度 40 字节。测宽和绘制共用字形 advance。
- 原生绘制不能按普通 o32 调用约定猜参数；新增帧按 16 字节对齐，并完整保存 128 位被调用者保存寄存器。
- 不能把注入段放在启动 BSS 清零区域。当前代码起于 `0x6DE100`，堆起点保留到 `0x6DF000`。
- 崩溃根因：只改 `SetupHeap` 不够，`0x3F6B78` 与 `0x405C44` 两个初始化堆指针也必须同步。旧方案会让堆分配覆盖代码。
- NORK 头 `+16` 是文件条目数量；新增字体别名时必须同步，原有资源偏移保留。新字体负载按 128 字节对齐，ISO 按 2048 字节扇区对齐。
- BASE.X 增长后必须更新 ISO 根目录、双端序尺寸、卷扇区数，并移动/更新 `DIR_LIST.LST` 中缓存的 BASE.X 尺寸。
- 共用断行函数保留 GBK 字符边界，避免闭合标点出现在软换行后的行首，并避免开括号留在行尾；极窄到容不下不可分标点组的宽度优先保证前进。

## 版本与验证范围

| 版本 | 已有证据 | 边界 |
|---|---|---|
| v0.2.3 | 实际后台严格解释/重编译、代表性菜单/教程/战役/HUD/目标、独立测试卡存读档。最重已观察场景主堆峰值 16,322,176 字节，最低空闲 9,756,916 字节。 | 不是整个游戏或整机所有内存的上界，不是实体机验收。 |
| v0.2.4 | 36 条教程目标复核、19 条修订、标点禁则和静态镜像检查。 | 未启动模拟器。 |
| v0.2.5 | 全部 35 条单位名复核、5 条统一；三套字体各补“吉”，保留所有旧字形；902 种必需可打印编码无缺字。 | 未启动模拟器，未重测峰值。 |

v0.2.5 的三套字体各 1,063 条字形，纹理页仍为 15／40／15，堆保留仍为 3,956 字节。历史主机检查覆盖 131,073 个解码、2,724 个测宽、29,056 个断行与 1,449 个标点边界案例。最终镜像独立回读验证 115 个 ISO 目录项和 40 处字体绑定。

历史镜像 SHA-256（镜像不随提交提供）：

```text
v0.2.3 c98166affb7edda9832cf269f41f7dcdbc29479aa7c49877b49350b7f07de2d7
v0.2.4 b2d155830d8e7052ef7d388a59b698052583f14d32f9a98056c55abbcdbe32dc
v0.2.5 10ad811c124c45c48fd02a9d4166f7d1023fdfe8286a9c8b8ebb5c54b63b4ea7
```

仍有 52 处动态/继承布局不能由静态审计证明；格式化参数长度、完整战役、最大规模战斗与实体 PS2 需要后续实际检查。本次源码导出只做语法和指令身份核对，不把原工程的游戏运行结果冒充为此快照的独立验收。
