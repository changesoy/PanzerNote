# Wave 8 主题体系验收记录（B9 B5，2026-09-09）

对应设计稿第十节（Golden Paths + Theme Coverage Matrix）的逐格验收成文。
状态图例：✅ = 已通过（测试/自动化）；⏳ = 待人工 UI 过一遍（B5-2，用户侧确认）。

## 0.1 分支级代码审查结论（2026-09-09，pre-merge）

分支 review（`feat20260816-theme_foundation` vs main，40 commit / 119 文件）结论 **READY WITH NOTES
（无 Blocker / 无 High）**。已当轮修复：

- **F-1**（原 Medium）`_load_palettes` palette 读取/解析异常非 ThemeError → 包装为 `ThemeParseError`
  （`manager.py`），保证 `request()` 统一走 `theme_commit_failed`，不穿透事务层导致 Snapshot Overlay 残留。
- **F-2**（原 Medium）`build_plan` 跨包切换 `new_map[key]` 潜在 KeyError → 改 `new_map.get(key, "")`
  （`transition.py`），对称于 `old_map.get(key, "")`。
- **F-5**（原 Low）`theme_commit_failed` 无监听 → main_window 连接并 `secretary.show_message` 失败反馈。

**延后至 B8（多包化时必现，当前 default 单包不触发）**：

- **F-3** `ThemeValidator` 不强制 token 全覆盖 / recipe style 键集合 → QSS 生成期硬索引可能 KeyError。
  B8 引入真实第二个主题包前，应让 `_validate_tokens` 强制白名单 token 全覆盖（或定义必选子集）、
  `_validate_recipes` 对 renderer 的 QSS builder 所需 style 键做 schema 校验。
- **F-4** `_retry_pending` 恢复路径只做 `prepare+commit`，不执行调用点收尾（config 持久化 / 全局 QSS 重涂 /
  DWM 标题栏）。当前生产注册 0 宿主不可达；B8 接入真实 RendererHost 时，应由 `theme_committed` 统一驱动
  全局重涂。

## 0. 自动化证据（基线）

- 全量 tiered pytest：**1448 passed**（2 warnings，44.2s，无超时）
  - 其中主题 v2 切换/事务/规划/冒烟子集：`test_theme_v2_switching / _manager / _transition / _smoke`
    = **52 passed**（含 B7 test-only renderer 的 L0/L1 验证、激活事务回滚、Safe Switch pending）
- 全量 mypy：**124 源文件零错误**
- offscreen 冒烟：QSS 无累积、行高随字体更新、主题加载 dark/light 双变体
- 深色遗漏像素探针：`scripts/check_dark_theme_gaps.py`（本地维护，gitignored）A/B/C/D 四组全绿
- 切换性能基准：`scripts/bench_theme_switch.py`（见 color_audit.md 性能审计段）

## 1. Golden Paths

| # | Golden Path | 状态 | 证据 |
| --- | --- | --- | --- |
| 1 | Default Dark / Default Density | ✅ 自动化 / ⏳ 目视 | v2 双变体加载 + 深色像素探针通过；目视外观待 B5-2 |
| 2 | Default Light / Default Density | ✅ 自动化 / ⏳ 目视 | 同 #1 |
| 3 | Second Theme Dark | 不适用 | 第二视觉语言（B8）已延后，仓库仅 default 单包 |
| 4 | Second Theme Light | 不适用 | 同 #3 |
| 5 | Default / Compact | ⏳ 目视 | density 档位存在（design.json），UI 侧未做自动断言 |
| 6 | Large File Mode | ✅ 自动化 | LFM 相关测试通过（全量 pytest 覆盖该模块） |
| 7 | Split View | ✅ 自动化 | 分屏相关测试通过（含重置分屏均分比例修复 commit 5a39867） |
| 8 | Theme L0 Switch | ✅ | L0 同包变体切换测试通过 + 基准 0.04ms（color_audit 性能审计段） |
| 9 | Theme L1 Switch | ✅（测试级） | B7 test-only renderer A→B 验证 host identity/signals/state（测试内，非产品路径；生产注册 0 宿主） |

## 2. Theme Coverage Matrix

| Surface | Default Dark | Default Light | Theme Recipe | Renderer 可变 | 验收 | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| Bootstrap / Pre-Main | ✓ | ✓ | Bootstrap | - | ✅ | `test_bootstrap_appearance.py` + FirstRunDialog 接入记录（color_audit 补漏 B） |
| Editor | ✓ | ✓ | ✓ | 部分 | ✅ 自动化 / ⏳ 目视 | B2 垂直切片测试 + 深色探针；目视待 B5-2 |
| Tabs | ✓ | ✓ | ✓ | ✓ | ✅ 自动化 / ⏳ 目视 | tab 相关测试 + 补漏 C recipe 收敛 |
| File Tree | ✓ | ✓ | ✓ | 部分 | ✅ 自动化 / ⏳ 目视 | B4 接入 + 拖拽测试 |
| Menu | ✓ | ✓ | ✓ | ✓ | ⏳ 目视 | 全局 QSS 驱动（B3） |
| Context Menu | ✓ | ✓ | ✓ | ✓ | ⏳ 目视 | 同 Menu |
| ComboBox | ✓ | ✓ | ✓ | ✓ | ⏳ 目视 | B3 Core Controls |
| Combo Popup | ✓ | ✓ | ✓ | ✓ | ⏳ 目视 | 全局 QSS + qt6_combo_popup workaround |
| Tooltip | ✓ | ✓ | ✓ | 部分 | ⏳ 目视 | 全局 QToolTip QSS |
| Dialog | ✓ | ✓ | ✓ | 部分 | ✅ 自动化 / ⏳ 目视 | 主题管理/快捷键/帮助等弹窗接入记录 |
| Settings | ✓ | ✓ | ✓ | - | ✅ 自动化 / ⏳ 目视 | B5 接入 + 深色探针 |
| Plugin Manager | ✓ | ✓ | ✓ | - | ✅ 自动化 / ⏳ 目视 | B5 接入 + 补漏 A/C |
| Secondary Window | ✓ | ✓ | ✓ | - | ✅ 自动化 / ⏳ 目视 | NativeTitleBarThemeFilter + 顶层窗口 DWM |
| Native File Dialog | OS | OS | - | - | OS | 原生 backend 走 OS 外观（设计稿 4.8 规则） |
| Game UI | 独立 | 独立 | - | - | 单独 | game_palette.json 独立配色（D13/D24，测试覆盖 game_palette） |

## 3. B5-2 人工 UI 回归清单（待用户过一遍后勾选）

逐项对照上面的 ⏳ 项：

- [ ] 启动首屏：暗/亮模式下 Bootstrap 首帧无白闪、字体正确、标题栏 C0 跟随
- [ ] Default Dark 目视：编辑器/标签栏/文件树/状态栏层级（#181818/#252526/#2B2B2B）清晰
- [ ] Default Light 目视：GitHub Light 风格观感、surface 层级可区分
- [ ] Compact 密度：设计变量密度档切换生效
- [ ] Large File Mode：打开 ≥1 万行文件，补全/折叠/Minimap/预览按阈值降级
- [ ] Split View：分屏布局、标签跨屏拖拽视觉（drop indicator/pressed/hover）
- [ ] 主题管理弹窗：色块/列表/分组标题深色下可读，无重叠
- [ ] 命令面板/搜索/查找替换：局部 QSS 与全局 recipe 一致，无白底浅字
- [ ] 菜单/右键菜单/ComboBox popup/Tooltip：深色下无浅色遗漏
- [ ] 切换主题：L0 过渡（Snapshot Overlay）正常；Reduced/Off 动效档位生效
- [ ] 游戏侧：主题切换不改变游戏画面；小秘书气泡随明暗（surface_raised/border_muted）

> 确认后把上表 ⏳ 改为 ✅ 并在 PR 验证段引用本文件。
