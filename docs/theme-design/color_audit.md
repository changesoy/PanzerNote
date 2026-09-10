# Color Audit

Baseline: fix20260703(3)-theme @ 78542d8875ba826cfdce256565aef55d003345a5

## Goal

This document records hardcoded colors and color-system inconsistencies.
This commit does not change runtime behavior.

## Reference Direction

PanzerNote dark theme should follow VS Code Dark Modern / Dark+ rather than JetBrains Darcula.

Reasons:

- Current editor background, selection color, Markdown preview code block, and `vscode_dark` highlighter already match VS Code more closely.
- JetBrains Darcula uses a warmer gray UI base such as #3C3F41, which would require a much broader palette migration.

## Allowed Hardcoded Colors

These are allowed for now:

| Area                                           | Reason                                                                                                         |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `src/themes/theme_engine.py`                   | Theme definitions are the source of truth                                                                      |
| `src/editor/highlight_themes.py`               | Syntax theme definitions are intentional palettes                                                              |
| `src/editor/syntax_highlighter.py`             | Markdown semantic highlighter palette; allowed but should stay aligned with VS Code                            |
| `src/editor/markdown_preview.py` HTML template | Self-contained rendered document CSS; allowed but should be gradually converted to explicit semantic variables |
| assets                                         | Real image/icon assets                                                                                         |
| tests                                          | Test fixtures                                                                                                  |

## Scan Patterns

Search patterns:

- `#[0-9a-fA-F]{3,8}`
- `rgb(`
- `rgba(`
- `QColor(`
- `setStyleSheet(`

Excluded paths:

- `src/themes/theme_engine.py`
- `src/editor/highlight_themes.py`
- `src/editor/syntax_highlighter.py`
- `assets/`
- `tests/`

## Summary

口径说明：以下计数为 **2026-09-09 B9 B2 复核实测**（`#[0-9a-fA-F]{3,8}` 含色行数，非旧基线
"处"数）。审计结论：**全库无绕过主题系统的裸硬编码色**——所有 hex 字面量均属下述
allowed 类别之一（v2 解析回退默认值 / 设计常量 / 游戏域常量 / 注释与降级路径）。

| File                                           | Count | Status             | Notes                                                                         |
| ---------------------------------------------- | ----: | ------------------ | ----------------------------------------------------------------------------- |
| `src/editor/markdown_preview.py`               |    28 | Allowed (fallback) | 全部为 v2_token/v2_color 回退默认值 + 模板失败降级 HTML 字面量（B8 注释标明） |
| `src/themes/bootstrap.py`                      |    18 | Allowed (design)   | BootstrapAppearance 色板常量（Layer 0，刻意不解析 Theme v2，见 4.8）          |
| `src/editor/syntax_highlighter.py`             |    17 | Allowed            | Markdown 语义色板（allowed 清单）；Pygments 语法色走共享 syntax palette       |
| `src/themes/theme_v2/consumer.py`              |    11 | Allowed (fallback) | v2_token/v2_color/v2_export_colors 的回退默认值（v2 不可用时才生效）          |
| `src/editor/editor.py`                         |    13 | Allowed (fallback) | gutter 书签/折叠等均为 v2 回退默认值（Batch B 已迁移 token 消费）             |
| `src/ui/shortcut_panel.py`                     |    10 | Allowed (fallback) | v2 回退默认值                                                                 |
| `src/editor/find_replace.py`                   |    10 | Allowed (fallback) | 搜索 match/current 已走 search 专用 token（Batch C），余下为回退默认值        |
| `src/game/game_sidebar.py`                     |     9 | Allowed (game)     | D13/D24 游戏域独立配色，走 game*palette.json（game*\* token）                 |
| `src/editor/editor_tabs.py`                    |     9 | Allowed (fallback) | v2 回退默认值                                                                 |
| `src/themes/theme_preview.py`                  |     8 | Allowed            | 色板 swatch 展示被预览主题的色值（`.get(key, "#000000")` 缺省），border 走 v2 |
| `src/ui/help_dialog.py`                        |     7 | Allowed (fallback) | v2 回退默认值                                                                 |
| `src/ui/side_panel_host.py`                    |     7 | Allowed (fallback) | 硬编码已移除（Batch C），余下为 v2 回退默认值                                 |
| `src/game/secretary_widget.py`                 |     5 | Allowed (game)     | D13/D24 游戏域独立配色，气泡/状态色走 game*palette.json（secretary*\* token） |
| `src/ui/command_palette.py`                    |     5 | Allowed (fallback) | hint/dialog/input 均 v2 回退默认值；QListWidget 由全局 tree_item recipe 驱动  |
| `src/editor/completion.py`                     |     5 | Allowed (fallback) | 容器/滚动条已迁 v2 recipe（补漏），选中色走 accent_soft token                 |
| `src/editor/minimap.py`                        |     4 | Allowed (fallback) | 半透明 alpha 为绘制细节，颜色来源走 recipe `viewport` 键（2026-08-17 修正）   |
| `src/game/resource_bar.py`                     |     4 | Allowed (game)     | D13/D24 游戏域独立配色                                                        |
| `src/editor/status_bar.py`                     |     4 | Allowed (fallback) | statusbar recipe 已收敛（补漏 C），余下为 v2 回退默认值                       |
| `src/main_window.py`                           |     3 | Allowed (fallback) | v2 回退默认值                                                                 |
| `src/editor/find_in_files_panel.py`            |     1 | Allowed (fallback) | text_secondary v2 回退；输入/下拉/结果树由 B3 全局 recipe 驱动                |
| `src/themes/theme_v2/transition_controller.py` |     1 | Allowed (fallback) | v2 回退默认值                                                                 |
| `src/ui/main_window_ui.py`                     |     1 | Allowed (fallback) | v2 回退默认值                                                                 |

> 复核方法：全库 `src/` 正则扫描 `#[0-9a-fA-F]{3,8}` + 逐文件分类；仅命中 1 处
> `QColor("#...")`/裸 QSS 色（`resource_bar.py` 分隔线，仍为 v2_token 回退）。

> 补充（2026-09-10，`refactor20260910-webengine_single_path`）：**导出/打印配色固定解析亮色变体**
> （`consumer.v2_export_variant_id` → `variant_for_dark(False)`），不再随当前激活主题取色；语法高亮同理由
> `highlight_code_html(..., variant_id)` 显式传入。目的是深色主题导出到白底 PDF/HTML 时保持白纸黑字。
> 该行为未新增任何 hex 字面量，上表 `consumer.py` 计数（11）不变。

## Unreasonable Color Arrangements

### 1. Mixed Material and VS Code accent systems

~~Current dark theme mixes Material-like `#BB86FC` / `#03DAC6` with VS Code-like editor, selection and code colors.~~

**RESOLVED (Batch E)**: Dark theme `primary` switched to VS Code blue `#0078D4`, `primary_dark`/`hover_bg` to `#026EC1`, `focus_border` to `#0078D4`.

### 2. `primary_light` is semantically overloaded

~~`primary_light` currently behaves like selection background.~~
**RESOLVED**: `selection_bg`, `selection_fg`, `hover_bg`, `active_bg` tokens added and wired.

### 3. Dark surface layers are too flat

~~Many surfaces use `#1E1E1E`.~~
**RESOLVED (Batch E)**: Dark theme now uses separate levels:

- window / title / status: `#181818`
- editor: `#1F1F1F`
- widget (sidebar): `#202020`
- card: `#2B2B2B`

### 4. Search highlight colors live in `find_replace.py`

~~Move later to: `search_match_bg`, `search_current_bg`, `search_current_fg`~~
**RESOLVED (Batch C)**: `find_replace.py` and `find_in_files_panel.py` now read from search tokens.

### 5. Gutter bookmark and fold marker colors live in `editor.py`

~~Move later to: `editor_bookmark_bg`, `editor_bookmark_fg`, `editor_fold_marker`, `editor_fold_marker_collapsed`~~
**RESOLVED (Batch B)**: `editor.py` now reads from bookmark/fold tokens.

### 6. Side panel selected state depends on `primary`

~~If `primary` remains `#BB86FC`, white text is not ideal.~~
**RESOLVED (Batch E)**: `primary` is now VS Code blue `#0078D4`; white text on blue is the intended contrast.

### 7. Markdown preview vs export duplicate layout CSS (Wave 1.5)

~~Preview template and export document each maintained a copy of the Markdown content
layout CSS (headings / table / code / list / quote …), drifting from each other over time.~~
**RESOLVED (Wave 1.5)**: single source `MARKDOWN_LAYOUT_CSS` in
`src/editor/secure_markdown_renderer.py`, consumed by both the preview template
(`markdown_preview.PREVIEW_HTML_TEMPLATE`) and the export document
(`build_export_html_document`). Colors are referenced via CSS variables
(`--text-primary` / `--border` / `--surface` …), injected from theme tokens by each consumer.

**Render path decision (Wave 1.5)**:

- Primary preview path: `markdown_preview.py` (markdown-it-py, with source-line injection / async highlight / local image resolution). Not a legacy renderer.
- Unified safe render + export entry: `secure_markdown_renderer.py`
  (`render_markdown_to_safe_html` / `render_plain_text_to_safe_html` /
  `build_export_html_document`), kept and used for HTML/PDF export, preview fallback,
  and `strip_dangerous_html` sanitization reused by the preview.
- Layout CSS that is allowed to stay local to each consumer: document shell (`body`),
  preview-only interactive styles (TOC / code-container / copy button / folding / scrollbar),
  export-only shell (`pre` simple blocks).

## Target Token Values (VS Code Dark Modern / Dark+)

PanzerNote dark theme targets VS Code Dark Modern / Dark+, not JetBrains Darcula.

| Token                                  |    Target | Usage                        |
| -------------------------------------- | --------: | ---------------------------- |
| `bg_window` / `bg_title` / `bg_status` | `#181818` | Shell, title bar, status bar |
| `bg_editor`                            | `#1F1F1F` | Editor viewport              |
| `bg_widget`                            | `#202020` | Sidebars, panels             |
| `bg_card` / `bg_codeblock`             | `#2B2B2B` | Cards, code blocks           |
| `bg_input`                             | `#313131` | Input fields                 |
| `primary`                              | `#0078D4` | Primary accent               |
| `primary_dark` / `hover_bg`            | `#026EC1` | Hover, pressed states        |
| `selection_bg`                         | `#264F78` | Selection background         |
| `focus_border`                         | `#0078D4` | Focus ring                   |
| `search_match_bg`                      | `#3A3D41` | Find match highlight         |
| `search_current_bg`                    | `#515C6A` | Current find match           |
| `search_current_fg`                    | `#FFFFFF` | Current find match text      |
| `editor_bookmark_bg`                   | `#0078D4` | Bookmark gutter marker       |
| `editor_bookmark_fg`                   | `#FFFFFF` | Bookmark gutter marker text  |
| `editor_fold_marker`                   | `#808080` | Fold marker (expanded)       |
| `editor_fold_marker_collapsed`         | `#C5C5C5` | Fold marker (collapsed)      |

### Batch Strategy

- **Batch A**: Add tokens only, with old values as defaults. No visible UI change.
- **Batch B / C / D**: Gradually wire components to use tokens.
- **Batch E**: After all components use semantic tokens, switch the built-in dark theme palette to these target values.

## Migration Batches

### Batch A: ThemeColorScheme semantic tokens ✅ COMPLETED

Added tokens with old values as defaults (no UI change):

- `selection_bg` → light: `#BBDEFB`, dark: `#264F78`
- `selection_fg` → light: `#212121`, dark: `#E0E0E0`
- `hover_bg` → light: `#BBDEFB`, dark: `#264F78`
- `active_bg` → light: `#1976D2`, dark: `#985EFF`
- `focus_border` → light: `#2196F3`, dark: `#BB86FC`
- `search_match_bg` → light: `#FFEE58`, dark: `#6B6B00`
- `search_current_bg` → light: `#FF9800`, dark: `#B47800`
- `search_current_fg` → light/dark: `#FFFFFF`
- `editor_bookmark_bg` → light: `#FF9800`, dark: `#BB86FC`
- `editor_bookmark_fg` → light/dark: `#FFFFFF`
- `editor_fold_marker` → light: `#4CAF50`, dark: `#81C784`
- `editor_fold_marker_collapsed` → light: `#66BB6A`, dark: `#A5D6A7`

_Note: Dark theme values match existing hardcoded colors in editor.py/find_replace.py to ensure zero visual change._

### Batch B: Editor auxiliary colors ✅ COMPLETED

Migrated:

- `editor.py`: fold markers → `editor_fold_marker` / `editor_fold_marker_collapsed`; bookmarks → `editor_bookmark_bg` / `editor_bookmark_fg`
- `syntax_highlighter.py`: Markdown semantic highlighter now reads from `md_*` theme tokens (h1-h6, code, link, quote, etc.)
- `minimap.py`: fallback colors aligned with theme defaults (`minimap_bg`, `border`, `text_disabled`, `primary`)

_Note: `find_replace.py` search highlights moved to Batch C (search tokens)._

### Batch C: Sidebar and command surfaces ✅ COMPLETED

Migrated:

- `side_panel_host.py`: audited, already fully token-driven (no hardcoded colors)
- `command_palette.py`: hint label fallback aligned with `text_secondary` default
- `find_in_files_panel.py`: text fallbacks aligned with `text_secondary`
- `game_sidebar.py`: `GameIconButton` colors wired to `game_build`/`game_garage`/`game_collection` tokens

### Batch D: Legacy Markdown renderer decision ✅ COMPLETED

`secure_markdown_renderer.py` still has active call paths (export_service, markdown_preview fallback). Kept as-is.
`markdown_preview.py` CSS refactored: `PREVIEW_HTML_TEMPLATE` hardcoded colors replaced with CSS variables; `_DARK_COLOR_MAP` and `_get_dark_preview_template` removed; `_build_preview_css_vars` injects `:root` overrides from theme tokens.

### Batch E: Palette normalization ✅ COMPLETED

Switched built-in dark theme palette to VS Code Dark Modern / Dark+ target values:

- `background`/`surface`: `#1E1E1E` → `#181818`
- `editor_bg`: `#1E1E1E` → `#1F1F1F`
- `sidebar_bg`: `#1E1E1E` → `#202020`
- `card`: `#2D2D2D` → `#2B2B2B`
- `primary`: `#BB86FC` → `#0078D4`
- `primary_dark`/`hover_bg`/`active_bg`: `#985EFF`/`#264F78` → `#026EC1`
- `focus_border`: `#BB86FC` → `#0078D4`
- `search_match_bg`: `#6B6B00` → `#3A3D41`
- `search_current_bg`: `#B47800` → `#515C6A`
- `editor_bookmark_bg`: `#BB86FC` → `#0078D4`
- `editor_fold_marker`: `#81C784` → `#808080`
- `editor_fold_marker_collapsed`: `#A5D6A7` → `#C5C5C5`
- `statusbar_bg`/`menubar_bg`: `#1E1E1E` → `#181818`

Light theme palette unchanged.

### Wave8 深色模式遗漏修复 ✅ COMPLETED

修复深色模式下浅色背景/文字遗漏（四个根因，规划书 `Wave8-深色模式修复规划书.md`）：

- **根因 1**（`theme_engine.py`）：`generate_stylesheet()` 运行时改取 `svc.active_variant()`
  （`use_active=True`），不再依赖 v1 遗留 `_active_theme_id` 推导明暗。修复后全局 QSS
  （主窗口背景、QLabel、QSplitter::handle、QFrame[frameShape] 分隔线、QDialog/QMessageBox）
  在运行时切换 dark 后同步变深，一处根因覆盖"主界面边框 / 分屏竖条 / 记事本设置 /
  快捷键列表 / 新手攻略 / 使用说明"等全部弹窗与结构遗漏。
- **根因 2**（`theme_v2/library.py` + `theme_engine.py` v1 回退）：QGroupBox 标题
  `margin-top` 8px → 16px、`padding-top` 16px → 6px、补 `subcontrol-position: top left`，
  修复"资源颜色（固定）"等标题与首行内容重叠。
- **根因 3**（`theme_preview.py`）：`_apply_theme_colors` 补齐 generic 选择器
  （QDialog/QLabel/QListWidget/QGroupBox/QPushButton/QScrollBar/QDialogButtonBox），
  主题管理弹窗深色下色块/列表/分组标题可读。
- **根因 4**（验证型修复）：offscreen 像素探针实测确认全局 `QFrame[frameShape]`
  `background-color` 规则在局部样式表嵌套下仍命中，9 处原生分隔线
  （resource_bar/status_bar/game_sidebar/file_tree）由全局规则自动覆盖，无需逐处糊样式。

回归工具：`scripts/check_dark_theme_gaps.py`（本地维护，gitignored），A/B/C/D 四组全绿。

### Wave8 补漏 A/B/C/D（2026-08-17）✅ COMPLETED

补漏规划 `Wave8-补漏规划.md` 四批次收尾，主题 token/recipe 语义修正汇总：

**补漏 A（P0 主题语义）**：`recipes.json` 7 处取值改为引用变体 token——
`editor.line_number → editor_line_number`（dark #858585 / light #BDBDBD）、
`editor.current_line → editor_current_line`（dark #2A2D2E / light #FFF9C4）、
`tab.hover_background / close_hover → border_muted`（浅色下可见）、
`tab.pressed_background → border_strong`、`scrollbar.handle_hover → border_muted`、
`markdown.code_block_bg → md_preview_code_block_bg`（与 `v2_export_colors` 导出链路同源，
消除预览/导出底色不一致）。

**补漏 B（Bootstrap/Pre-Main）**：新增 `src/themes/bootstrap.py` BootstrapAppearance，
Layer 0 启动期外观（固定浅色，色板常量与默认主题对齐，刻意不解析 Theme v2）；
FirstRunDialog 接入局部 QSS + C0 titlebar。

**补漏 C（B3/B4 体系收敛）**：新增 `statusbar` recipe（theme_engine 全局段与
status_bar.py 局部 QSS 收敛同源，消除 text_secondary/text_primary 双轨分歧）；
find_replace 局部美化删除、改由全局 recipe 驱动；tab/tree_item/command_palette/
side_panel_host 的 spacing/radius 走 design 变量；input placeholder 接线 QSS
`placeholder-text-color`（仅 QLineEdit）。

**补漏 D（B1/B2 契约加固）**：`ThemeResourceContract.validate_path` 增加 `exists()`
检查（B1 4.3：不存在的资源 activate 前报错）；minimap recipe `viewport` 接线
`minimap_viewport` 变体 token（替换原 accent+alpha 硬编码派生）。

**遗留专用 token 消费状态（P1-3 收敛说明）**：`editor_* / md_* / search_* /
minimap_viewport` 等遗留专用 token 保留在变体与白名单中，消费方矩阵：

- **recipe 引用（生产消费）**：`editor_line_number`、`editor_current_line`、
  `md_preview_code_block_bg`（+ 导出链路）、`minimap_viewport`
- **theme_preview 色板展示（定制表面，不驱动 UI）**：`editor_background`、
  `editor_bracket_*`、`editor_bookmark_*`、`editor_fold_marker*`、`md_*`、`search_*`
- B2 消费端统一走 recipe 语义 token（`surface_*` / `focus` / `accent` 等）；
  如需让某专用 token 生效，应改 recipe 引用（如补漏 A 的做法），而非在消费端直读 token。

**2026-08-17 用户实测修正（补漏 D 后续）**：

- 深色层级修正采用 **A 方案**：dark `surface_secondary` #181818 → **#252526**。
  原因：dark 变体 `surface_primary` 与 `surface_secondary` 原均为 #181818，导致
  标签栏/非活动 tab/文件树侧栏/状态栏/查找栏等"第二级表面"与正文无法区分；
  浅色下两者有区分（#FFFFFF / #F5F5F5），结构正常。改后层级：
  `surface_primary` #181818（正文/活动 tab）< `surface_secondary` #252526
  （标签栏/非活动 tab/侧栏/状态栏等）< `surface_raised` #2B2B2B。
- tab 背景保持**单一接口**：`tab.background` recipe 直接引用 `surface_secondary`
  （曾临时引入 `tab_inactive_background` 专用 token，因值与 surface_secondary
  相同、观感一致，按"单一真相源"原则移除，避免冗余接口）。
- minimap 视口恢复"浅色半透明矩形"观感：`minimap.py` 填充 alpha 90 / 边框 alpha 150
  （半透明是绘制细节，颜色来源仍走 recipe `viewport` 键）；`minimap_viewport`
  值调整使半透明叠加后双变体均可见——dark `#3C3C3C` → `#6E6E6E`、light
  `#E0E0E0` → `#9E9E9E`。

## 性能审计（B9 B1-1，2026-09-09）

基准脚本：`scripts/bench_theme_switch.py`（offscreen，`--iter N` 可调）。测量结果（本机，iter=20）：

| 环节                                                             | 耗时     |
| ---------------------------------------------------------------- | -------- |
| cold load（默认包加载 + 全量校验，启动期单次）                   | 10.0 ms  |
| L0 prepare（同包变体切换，复用当前 snapshot）                    | ~0.00 ms |
| L0 commit（激活事务，无 QWidget 副作用）                         | ~0.00 ms |
| QSS rebuild（ThemeComponentLibrary.all_qss，\_apply_theme 主体） | 0.04 ms  |
| 单次 L0 切换合计（prepare + commit + qss rebuild）               | ~0.04 ms |

**结论（对应设计稿 4.4）**：同步实现满足"第一版同步实现，仅 profiling 证明必要时才把纯数据
解析移出 GUI thread"的约定，**无需异步化**。理由：

- 生产路径恒 L0（产品注册 0 个 RendererHost），prepare 复用当前 snapshot 且只校验
  variant 存在，数据解析成本可忽略；
- 跨包流水线（loader + validator 六阶段）是 L1/新包路径，当前仓库仅 default 单包、
  生产不触发，且 B8 第二视觉语言已延后——待真实第二包出现时再测该路径；
- 全局 QSS 重建 0.04 ms 远低于一帧预算（16 ms @60fps），repaint 成本不构成卡顿。

风险留档：若未来 B8 引入第二视觉语言（跨包 L1 路径），prepare 将首次经过完整
loader/validator 流水线，需按同脚本复测；若测得单次 >16ms 再评估异步化。

## Verification Checklist

- Start app in dark theme.
- Restart while dark theme is persisted.
- Open `.md` file and verify preview is not blank.
- Open `.py` file and verify syntax highlight.
- Trigger completion popup.
- Open theme manager.
- Open command palette.
- Open find/replace bar.
- Open find-in-files panel.
- Toggle sidebar panels.
- Dark mode: verify resource bar / sidebar / status bar separators are dark, not light.
- Dark mode: open theme manager, verify swatch labels and group titles readable, no overlap.
