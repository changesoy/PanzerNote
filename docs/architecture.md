# PanzerNote 架构与设计文档

> 本文档面向开发者和 AI，描述项目的目标、代码结构、核心模块、数据流与架构约束。
> 用户使用指南、版本变更、未完成规划请参考 [../README.md](../README.md)、[../CHANGELOG.md](../CHANGELOG.md)、[roadmap.md](roadmap.md)。

---

## 1. 项目背景

PanzerNote 是一款以已停服二次元游戏《战车少女》（PanzerMaiden）为主题的 **PC 端离线单机记事本程序**，用于私人纪念。核心理念：

- **记事本为主体**：功能完整的多标签文本编辑器，支持 Markdown 分屏预览与 30+ 语言语法高亮
- **游戏系统为灵魂**：通过日常书写行为积累资源 → 资源投入建造 → 抽取战车娘角色 → 点亮图鉴
- **小巧、离线、本地存档**：所有数据存储在本地 JSON 文件中，不依赖网络

**技术栈**：Python 3.11+ / PyQt6 / Pygments / markdown 库 / markdown-it-py / WebView2（PyWinRT 绑定 + qasync 事件循环合并）

---

## 2. 模块状态总览

| 模块                 | 状态      | 说明                                                                                                                                                         |
| -------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 多标签文本编辑器     | ✅ 完成   | 行号、语法高亮、自动缩进、括号配对、括号匹配高亮、行操作、大小写转换、转到行、JSON/XML 格式化                                                                |
| 缩进/行尾配置        | ✅ 完成   | indent_size/use_tabs 配置；LF/CRLF 探测与规范化；状态栏切换行尾格式                                                                                          |
| 文本统计             | ✅ 完成   | CJK 按字计数 + 拉丁按词计数；状态栏信号驱动统计                                                                                                              |
| Markdown 分屏预览    | ✅ 完成   | 实时渲染 + 代码块高亮 + 一键复制 + 本地图片 + 源码行号同步 + 折叠同步                                                                                        |
| 代码缩略图 (Minimap) | ✅ 完成   | 鸟瞰图、点击/拖拽导航、块级缓存增量失效、跳过折叠隐藏块                                                                                                      |
| 大文件性能优化       | ✅ 完成   | Wave 4 E：运行时探针埋点（perf_probe）、lazy 高亮 Document 级多 View 协作（visibleRanges = ∪）、Large File Mode 达阈值自动降级（可配置可回退）、阈值自动启用 |
| Markdown 标题折叠    | ✅ 完成   | 标题层级折叠 + 代码缩进折叠 + 工作区持久化 + 跳转自动展开                                                                                                    |
| Markdown 大纲导航    | ✅ 完成   | 解析标题树、点击跳转、按文件类型显隐                                                                                                                         |
| 命令面板             | ✅ 完成   | Ctrl+Shift+P / F1 唤起、搜索执行命令、位置记忆                                                                                                               |
| 跨文件搜索           | ✅ 完成   | 后台线程遍历 + 正则/纯文本匹配 + 按文件分组 + 双击跳转                                                                                                       |
| 文档缓冲区自动补全   | ✅ 完成   | 词频匹配 + Enter/Tab 接受 + IME 组字期间不弹出                                                                                                               |
| 增强型查找替换       | ✅ 完成   | 正则、大小写敏感、全词匹配、匹配计数、ExtraSelections 高亮                                                                                                   |
| 侧栏面板宿主         | ✅ 完成   | 多面板注册/切换/宽度记忆                                                                                                                                     |
| 文件树               | ✅ 完成   | 文件树 + 外部文件区 + 右键菜单 + 接受标签拖拽移动文件                                                                                                        |
| 标签页拖拽           | ✅ 完成   | 标签内排序 + 拖拽到文件树移动文件                                                                                                                            |
| 分屏多视图           | ✅ 完成   | 分屏布局/状态持久化、方向切换、跨分屏标签拖拽、共享 Document 跨面板联动编辑（同一文档多视图）                                                                |
| 资源栏               | ✅ 完成   | 四资源显示 + 打字统计                                                                                                                                        |
| 在线/离线挂机        | ✅ 完成   | 在线每分钟 +5/+5/+5、铝材每3分钟+5；离线 1/3 向大取整，上限 24h                                                                                              |
| 打字奖励             | ✅ 完成   | textChanged 接入 → 递减收益算法 → 资源奖励（1:1:1:0.2）                                                                                                      |
| 每日签到             | ✅ 完成   | 每日首次启动发放奖励（各+100）                                                                                                                               |
| 小秘书               | ✅ 完成   | 立绘 + 台词气泡 + 事件台词 + 自定义角色/皮肤/状态                                                                                                            |
| 书签持久化           | ✅ 完成   | 书签保存到 workspace.json，关闭重开后恢复                                                                                                                    |
| 设置系统             | ✅ 完成   | settings.json + workspace.json + savegame.json，首次运行对话框                                                                                               |
| 安全防护体系         | ✅ 完成   | 路径验证/文件操作安全/输入验证/拖放白名单                                                                                                                    |
| 插件系统             | ✅ 完成   | 能力声明制（capabilities→权限映射）/命名空间式 PluginContext/主线程模型/数据与事件能力/热加载，2 个示例插件 + API 文档                                       |
| 主题系统             | ✅ 完成   | Theme v2（default 主题包/recipe 组件库/双变体）/全局 QSS 生成/预览/ThemeAwareMixin 全局生效/原生标题栏深色                                                   |
| 集中式版本管理       | ✅ 完成   | `src/__init__.py` 唯一真相源 + `verify_version.py` 一致性验证                                                                                                |
| 帮助中心             | ✅ 完成   | 帮助对话框（使用说明 + 新手攻略双页签）；内容存于 `data/help/*.md`，安全渲染；主题跟随 Theme v2 token（深浅色自适应）                                        |
| 建造系统             | 🔲 规划中 | 详见 [roadmap.md](roadmap.md)                                                                                                                                |
| 图鉴系统             | 🔲 规划中 | 详见 [roadmap.md](roadmap.md)                                                                                                                                |
| 车库系统             | 🔲 规划中 | 详见 [roadmap.md](roadmap.md)                                                                                                                                |
| 游戏设置界面         | 🔲 规划中 | 详见 [roadmap.md](roadmap.md)                                                                                                                                |

---

## 3. 目录结构

```
PanzerNote/
├── main.py                         # 程序入口（高DPI、字体、图标、首次运行引导、启动分析、版本一致性检查）
├── pyproject.toml                  # 项目配置（构建/依赖/pytest/mypy/动态版本引用）
├── .gitignore                      # Git 忽略规则
├── .gitattributes                  # Git 属性（* text=auto eol=lf 行尾符统一）
├── user_data_path.txt              # 持久化用户数据路径
├── CHANGELOG.md                    # 版本变更记录
├── LICENSE                         # GPL-3.0 许可证
│
├── tests/                          # 单元测试 + 性能基准测试（tests/benchmarks/）
│
├── src/                            # ══════ 源代码 ══════
│   ├── __init__.py                 # 版本号唯一真相源（__version__/get_version_tuple）
│   ├── main_window.py              # 主窗口协调者（两阶段关闭/会话恢复协调/信号回调/窗口事件/命令面板/插件主题集成；动作经控制器一行委托）
│   │
│   ├── core/                       # ── 核心模块 ──
│   │   ├── config.py               # 配置门面（委托 PathResolver/SettingsStore/WorkspaceStore/SavegameManager/SecurityManager，对外保持完整接口）
│   │   ├── path_resolver.py        # 路径解析（base_path / user_data_path.txt / 目录 getter + JSON 工具）
│   │   ├── settings_store.py       # 设置存储（settings dict / 命名空间设置 / reset_to_defaults）
│   │   ├── workspace_store.py      # 工作区存储（workspace dict / 会话状态 / 书签 / 折叠 / 关闭标签记忆）
│   │   ├── app_context.py          # 应用上下文容器（持有已拆子模块，供服务层组装）
│   │   ├── shared_document.py      # 共享文档模型（SharedDocument 拥有 QTextDocument + ViewState + SaveSnapshot）
│   │   ├── document_registry.py    # 全局文档注册表（document_id/路径索引/View 关联/生命周期 release）
│   │   ├── document_view_binding.py # View↔Document 信号接线器（attach/detach 幂等，生命周期随 View）
│   │   ├── workspace_entries.py    # workspace 序列化适配层（SharedDocument ↔ entry，schema 不变；3.5.10 未命名条目）
│   │   ├── session_restore_service.py # 会话恢复服务（崩溃恢复检测 / 恢复计划 / 恢复执行）
│   │   ├── config_import_service.py # 配置导入服务（类型校验 + 白名单，复用 WorkspaceStore 白名单）
│   │   ├── savegame_manager.py     # 存档管理器（加载/保存/每日签到/只读视图防泄漏）
│   │   ├── security_manager.py     # 安全管理器（PathValidator/FileGuard/InputValidator 集成管理）
│   │   ├── timer_manager.py        # 定时器管理中心
│   │   ├── event_bus.py            # 事件路由系统
│   │   ├── menu_builder.py         # 菜单构建器（已接入 ShortcutManager）
│   │   └── shortcut_manager.py     # 快捷键管理器
│   │
│   ├── editor/                     # ── 编辑器模块 ──
│   │   ├── editor.py               # 核心编辑器（行号、缩略图、语法高亮、自动缩进、虚拟滚动）
│   │   ├── editor_tabs.py          # 多标签管理（打开/保存/关闭/编码检测/拖拽迁移/共享 Document View 生命周期）
│   │   ├── editor_actions.py       # 行操作/大小写转换/JSON/XML 格式化（Mixin）
│   │   ├── auto_pair_handler.py    # 括号/引号自动配对（Mixin，frozenset 快速过滤）
│   │   ├── bracket_matcher.py      # 括号匹配高亮（纯函数，扫描配对位置，支持中英文括号）
│   │   ├── indentation.py          # 缩进统一入口（缩进宽度/缩进文本，禁止硬编码）
│   │   ├── eol_utils.py            # 行尾探测与规范化纯函数（LF/CRLF/CR）
│   │   ├── text_stats.py           # 文本统计纯函数（CJK 按字计数 + 拉丁按词计数）
│   │   ├── folding.py              # 折叠管理器（Markdown 标题折叠 + 代码缩进折叠）
│   │   ├── outline_parser.py       # Markdown 标题解析器（纯函数，提取标题层级与行号）
│   │   ├── outline_panel.py        # Markdown 大纲导航面板（QTreeWidget 展示标题树）
│   │   ├── completion.py           # 文档缓冲区自动补全（词频匹配 + IME 组字期间不弹出）
│   │   ├── find_in_files_service.py # 跨文件搜索后台服务（QThread 遍历 + 正则/纯文本匹配）
│   │   ├── find_in_files_panel.py  # 跨文件搜索结果面板（按文件分组 + 双击跳转）
│   │   ├── save_task.py            # 后台文件保存任务（SaveTask + QThreadPool 异步写入）
│   │   ├── save_task_manager.py    # 保存任务管理器（dirty→saving→clean/save_failed 状态机）
│   │   ├── temp_session_manager.py # 临时会话恢复（异常退出 autosave 恢复；autosave 读写经 FileGuard）
│   │   ├── virtual_scroll.py       # 虚拟滚动管理器（大文件延迟语法高亮；Wave 4 E2：Document 级多 View 协作）
│   │   ├── async_highlight.py      # 异步代码高亮渲染器（QThread + 任务队列）
│   │   ├── incremental_renderer.py # 渲染缓存（MD5 哈希缓存，全文级）
│   │   ├── document_render_cache.py # Markdown HTML render cache（Wave 4 C：Document 改动渲染一次、多 View 共用）
│   │   ├── syntax_highlighter.py   # 语法高亮（Pygments 适配器 + Markdown 专用高亮器）
│   │   ├── highlight_themes.py     # 代码高亮主题
│   │   ├── web_preview.py          # Web 预览适配器接口（8 项能力；后端可替换）
│   │   ├── web_preview_webview2.py # WebView2 后端实现（PyWinRT + WebView2 Runtime）
│   │   ├── webview2_runtime.py     # WebView2 Runtime 可用性检测（只读注册表 + 安装指引）
│   │   ├── markdown_preview.py     # Markdown 分屏预览（源码行号同步 + 代码块高亮 + 本地图片）
│   │   ├── minimap.py              # 代码缩略图（块级缓存增量失效）
│   │   ├── find_replace.py         # 查找替换栏
│   │   ├── search_service.py       # 搜索服务（QTextDocument.find 权威光标 + 从后向前替换）
│   │   ├── extra_selection_manager.py # 高亮层管理（统一 ExtraSelection 避免互相覆盖）
│   │   ├── secure_markdown_renderer.py # 安全 Markdown 渲染（清洗 script/iframe/onerror/javascript:）
│   │   ├── math_render.py          # 数学公式资源（KaTeX vendor 读取 + 字体 data URI + 注入片段 + has_math）
│   │   ├── mermaid_render.py       # 图表资源（Mermaid vendor 读取 + 懒注入/外置注入片段 + 就绪信号）
│   │   ├── export_service.py       # 导出服务（HTML/PDF 统一安全管线）
│   │   ├── file_open_service.py    # 文件打开安全入口（来源校验/路径白名单/二进制检测）
│   │   ├── file_action_controller.py # 文件动作编排（打开对话框/外部文件注册/最近文件过滤）
│   │   ├── edit_action_controller.py # 编辑动作编排（撤销/剪贴板/查找/行操作/大小写/书签/折叠，22 个方法）
│   │   ├── export_action_controller.py # 导出动作编排（PDF/HTML，均经 FileGuard 安全写入）
│   │   ├── settings_action_controller.py # 设置动作编排（对话框应用/导出/导入/保存/重置，show 与 apply 共享）
│   │   ├── editor_settings_dialog.py # 记事本设置对话框
│   │   ├── file_tree.py            # 文件树
│   │   └── status_bar.py           # 状态栏
│   │
│   ├── game/                       # ── 游戏模块 ──
│   │   ├── game_engine.py          # 挂机收益计算引擎
│   │   ├── resource_bar.py         # 资源栏 UI
│   │   ├── game_sidebar.py         # 游戏侧边栏
│   │   └── secretary_widget.py     # 小秘书组件
│   │
│   ├── ui/                         # ── UI 组件 ──
│   │   ├── main_window_ui.py       # UI 组装（MainWindowUIBuilder：顶层 widget 创建与布局，BuiltUI 返回 17 组件，不连业务信号）
│   │   ├── view_coordinator.py     # 视图协调器（ViewCoordinator：视图/分屏/面板切换，_current_view/_split_tabs 状态）
│   │   ├── unsaved_files_dialog.py # 未保存文件确认对话框（VS Code 风格单级确认，单/多文件共用）
│   │   ├── selection_clear_filter.py # 选中高亮清除过滤器（SelectionClearFilter：点击列表外空白清除选中）
│   │   ├── first_run_dialog.py     # 首次运行对话框
│   │   ├── command_palette.py      # 命令面板（Ctrl+Shift+P / F1 唤起，搜索并执行命令）
│   │   ├── side_panel_host.py      # 侧栏面板宿主（管理多面板注册/切换/持久化）
│   │   ├── shortcut_panel.py       # 快捷键提示面板
│   │   └── help_dialog.py          # 帮助对话框（双页签：使用说明/新手攻略；Markdown 内容 + Theme v2 主题适配）
│   │
│   ├── security/                   # ── 安全模块 ──
│   │   ├── __init__.py             # 安全模块导出与异常定义
│   │   ├── path_validator.py       # 路径安全验证
│   │   ├── file_guard.py           # 文件操作安全控制
│   │   ├── file_access_context.py  # 文件访问上下文枚举
│   │   └── input_validator.py      # 输入验证框架
│   │
│   ├── plugins/                    # ── 插件系统 ──
│   │   ├── plugin_base.py          # 插件基类、PluginMeta、PluginPermission、状态枚举
│   │   ├── capability_registry.py  # 能力注册/授权/调用（capabilities→权限两层结构）
│   │   ├── plugin_context.py       # 命名空间式 PluginContext（ctx.app/settings/savegame/…）
│   │   ├── plugin_event_bus.py     # 插件事件总线（白名单/节流/订阅上限）
│   │   ├── plugin_manager.py       # 插件管理器（扫描/加载/激活/停用/卸载/热加载）
│   │   └── plugin_manager_dialog.py # 插件管理对话框
│   │
│   ├── themes/                     # ── 主题系统 ──
│   │   ├── theme_engine.py         # 主题引擎（Theme v2 装配/全局 QSS 生成）
│   │   ├── theme_aware_mixin.py    # 主题感知混入
│   │   ├── theme_preview.py        # 主题预览对话框
│   │   └── theme_v2/               # Theme v2 运行时（service/manager/loader/validator/library 等 18 个模块）
│   │
│   └── utils/                      # ── 工具模块 ──
│       ├── logger.py               # 结构化日志系统
│       ├── exceptions.py           # 统一异常处理 @safe_call
│       ├── error_handler.py        # 统一错误提示系统
│       ├── dpi_helper.py           # 高 DPI 缩放适配
│       ├── feature_flags.py        # Feature Flag 系统
│       ├── window_theme.py         # Windows 原生标题栏深色辅助（DWM 非客户区）
│       ├── lazy_loader.py          # 启动性能分析（StartupProfiler）
│       └── perf_probe.py           # 运行时性能探针（Wave 4 E1：大文件加载/首屏/滚动热路径计时）
│
├── scripts/
│   ├── verify_version.py           # 版本一致性验证工具
│   ├── build_package.py            # 源码发布包构建（dist/PanzerNote-<ver>-src.zip）
│   └── bench_theme_switch.py       # 主题切换性能基准（B9：cold load / L0 / QSS 重建）
│
├── docs/                           # 文档
│   ├── architecture.md             # 本文件
│   ├── roadmap.md                  # 未完成规划
│   └── theme-design/               # 主题设计
│       ├── color_audit.md          # 硬编码颜色审计 + 性能审计（B9）
│       ├── wave8_acceptance.md     # Wave 8 验收记录（Golden Paths + Coverage Matrix + review 结论）
│       └── theme_authoring.md      # Theme v2 主题作者指南（主题包格式与校验规则）
│
├── THIRD_PARTY_NOTICES.md          # 第三方依赖许可证清单（B9 license 合规）
│
├── data/                           # 数据 & 资源（程序目录）
│   ├── assets/
│   │   ├── icons/
│   │   └── portraits/              # 角色立绘
│   ├── help/
│   │   ├── manual.md               # 使用说明（帮助对话框"使用说明"页签内容）
│   │   └── guide.md                # 新手攻略（帮助对话框"新手攻略"页签内容）
│   └── gamedata/
│       ├── characters.json         # 角色数据库
│       └── secretary_lines.json    # 小秘书台词配置
│
├── plugins/                        # 插件目录
│   ├── hello_panzer/               # 基础功能示例插件
│   ├── word_counter/               # UI 扩展示例插件
│   └── plugin_api.md               # 插件开发技术文档
│
└── notebooks/                      # 用户笔记库（用户数据路径下，首次运行创建）

    ── 以下目录位于用户数据路径（非项目源码目录），由 ensure_directories() 创建 ──

    {用户数据路径}/
    ├── notebooks/                  # 用户笔记库
    ├── data/config/
    │   ├── settings.json           # 编辑器/游戏/小秘书/视图/窗口设置
    │   └── workspace.json          # 会话状态
    ├── data/gamedata/
    │   └── savegame.json           # 游戏存档
    └── temp/autosave/              # 自动保存暂存区
```

---

## 4. 核心模块详解

### 4.1 配置管理（Config 门面 + 四个子模块）

Config 类从配置中枢演进为**门面（Facade）**：对外保持自 v1.6.x 起的完整接口不变（调用方零改动），内部把职责拆分委托给独立模块（hotfix 阶段 0/7）。拆分后的模块：

| 模块                       | 职责                                                                                                                                         |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `core/path_resolver.py`    | 路径解析：`base_path` / `_app_dir` / `user_data_path.txt` / 各目录 getter + JSON 读写工具（`load_json`/`save_json`/`merge_dicts`）           |
| `core/settings_store.py`   | settings.json：settings dict + 五个命名空间 getter/setter + `reset_to_defaults()`                                                            |
| `core/workspace_store.py`  | workspace.json：workspace dict + 会话状态/书签/折叠/关闭标签记忆 + `update_workspace_field()`（白名单由 `DEFAULT_WORKSPACE` 派生，单一来源） |
| `core/savegame_manager.py` | 存档管理（拆分于更早版本，继续由 Config 组合委托）                                                                                           |
| `core/security_manager.py` | 安全管理（拆分于更早版本，继续由 Config 组合委托）                                                                                           |

| 文件             | 位置                         | 职责                                                           | 管理者            |
| ---------------- | ---------------------------- | -------------------------------------------------------------- | ----------------- |
| `settings.json`  | `{base_path}/data/config/`   | 所有用户偏好设置（编辑器、游戏、小秘书、视图、窗口、快捷键）   | `SettingsStore`   |
| `workspace.json` | `{base_path}/data/config/`   | 会话状态（打开文件/最近文件/外部文件/书签/折叠/关闭标签记忆）  | `WorkspaceStore`  |
| `savegame.json`  | `{base_path}/data/gamedata/` | 游戏存档（四资源、核心数、打字统计、建造队列、拥有角色、成就） | `SavegameManager` |

**路径机制（方案A）**：

- 程序目录下保存 `user_data_path.txt`，记住用户选择的数据存储路径
- 首次运行由 `FirstRunDialog` 引导选择
- 资源文件（立绘、图标等）始终从**程序目录** `_app_dir` 读取
- 用户数据（笔记、配置、存档）从 `_base_path` 读取

**AppContext 装配**（`core/app_context.py`，hotfix 阶段 7）：

- `main.py` 创建 `Config` 后组装 `AppContext`（持有 `path_resolver` / `settings_store` / `workspace_store` / `config` 门面引用），传入 `MainWindow`
- `MainWindow` 保留 `self.config` 门面（过渡期共存）；服务层（`SessionRestoreService` / `FileActionController`）经 `app_context.workspace_store` / `app_context.path_resolver` 直连子模块
- 新代码鼓励使用 `app_context.<子模块>` 直连，避免继续穿透门面

**防泄漏约定**（与 SavegameManager 相同的只读策略）：

- `SavegameManager` 通过 `MappingProxyType` 暴露只读存档视图，`get_resources()` 返回拷贝
- `SettingsStore.as_dict()` / `WorkspaceStore.as_dict()` 返回**深拷贝**，杜绝调用方绕过封装修改内部状态
- `migrate_bauxite_counter` 迁移逻辑使用显式 API（读删 settings 命名空间），不依赖泄漏引用

**关键方法**：

- `_merge_dict(default, current)` — 递归合并，确保新增配置项向下兼容
- `get_resources()` / `add_resource()` — 资源 CRUD（委托 SavegameManager）
- `get_today_chars_typed()` — 自动按日期重置计数器（委托 SavegameManager）
- `update_last_login()` — 离线收益的时间基准（委托 SavegameManager）

### 4.2 主窗口 (`main_window.py`)

**布局结构**（从上到下、从左到右）：

```
┌──────────────────────────────────────────────────────┐
│  ResourceBar（资源栏：燃料/弹药/钢材/铝材 + 统计）    │
├──────────────────────────────────────────────────────┤
│  GameSidebar │ QSplitter                             │
│  (50px固定)  │ ┌─────────┬─────────────────────────┐ │
│  ← 返回      │ │FileTree │ FindReplaceBar (隐藏)   │ │
│  建 建造     │ │(可折叠)  │ EditorTabWidget          │ │
│  库 车库     │ │          │  ┌───┬───┬───┐           │ │
│  鉴 图鉴     │ │          │  │Tab│Tab│Tab│           │ │
│              │ │          │  ├───┴───┴───┤           │ │
│              │ │          │  │ Editor /   │           │ │
│              │ │          │  │ MD Preview │           │ │
│              │ │          │  │        ┌──┐│           │ │
│              │ │          │  │   小秘书│  ││           │ │
│              │ └─────────┴──┴────────┴──┘│           │ │
├──────────────┴──────────────────────────────────────┤
│  StatusBar（行/列 | 字符数 | 编码 | 文件类型）        │
└──────────────────────────────────────────────────────┘
```

**拆分后的模块职责**：

| 模块                                   | 职责                                                                                                                                                                                                                                                             |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --- |
| `main_window.py`                       | 主窗口协调者（~1255 行）：两阶段关闭、会话恢复协调、信号回调、拖放/键盘事件、命令面板、插件/主题集成、统一窗口显示入口（`present()`）；动作经控制器一行委托                                                                                                      |
| `ui/main_window_ui.py`                 | `MainWindowUIBuilder`：顶层 widget 创建与布局（17 个组件经 `BuiltUI` 返回），不连接业务信号                                                                                                                                                                      |
| `ui/view_coordinator.py`               | `ViewCoordinator`：视图/分屏/面板切换编排；`_current_view`/`_split_tabs` 状态；分屏状态持久化（3.5.2）、方向切换（3.5.6）、`close_split` 统一未保存确认（3.5.7）、空分屏自动关闭与布局重置（3.5.9）；依赖全构造注入，回调（信号连接/菜单同步）由 MainWindow 注入 |
| `ui/selection_clear_filter.py`         | `SelectionClearFilter`：应用级事件过滤器，点击列表外空白清除选中高亮                                                                                                                                                                                             |
| `editor/edit_action_controller.py`     | `EditActionController`：22 个编辑动作（撤销/剪贴板/查找/行操作/大小写/书签/折叠）                                                                                                                                                                                |
| `editor/export_action_controller.py`   | `ExportActionController`：PDF/HTML 导出（均经 FileGuard 安全写入，含 PDF 回调 `_on_pdf_generated`）                                                                                                                                                              |     |
| `editor/settings_action_controller.py` | `SettingsActionController`：设置动作编排（对话框应用/导出/导入/保存/重置，show 与 apply 共享 `_apply_editor_dict`）                                                                                                                                              |
| `editor/web_preview.py`                | Web 预览适配器接口（8 项能力：加载完成 / JS 执行 / 双向消息 / 资源根目录 / PDF 导出 / 显示控制）；`create_preview_adapter()` 恒返回 WebView2 后端                                                                                                                |
| `editor/web_preview_webview2.py`       | WebView2 后端实现（PyWinRT + qasync）：`navigate_to_string` / `execute_script_async` / `print_to_pdf_async` / 虚拟主机资源映射；初始化失败或 Runtime 缺失时在预览区显示可读提示                                                                                  |
| `editor/webview2_runtime.py`           | WebView2 Runtime 可用性检测：只读注册表（HKCU/HKLM EdgeUpdate 客户端键）读取版本，缺失时给出安装指引文案（不导入 PyWinRT、不访问网络）                                                                                                                           |
| `core/timer_manager.py`                | 定时器生命周期管理（自动保存/统计/挂机奖励）                                                                                                                                                                                                                     |
| `core/event_bus.py`                    | 信号连接集中管理，解耦模块间通信                                                                                                                                                                                                                                 |
| `core/menu_builder.py`                 | 菜单栏构建逻辑，已接入 ShortcutManager                                                                                                                                                                                                                           |
| `game/game_engine.py`                  | 挂机收益计算（在线/离线奖励、打字奖励、资源上限检查）                                                                                                                                                                                                            |

**行数基线**（Wave 3 A~E 五分支完成后的记录）：

- `main_window.py`：1669 行（重构前）→ **1255 行**（A~E 后，超出方案预期 1000~1150，属 Qt 主窗口协调者合理规模）。
- 拆分收益：编辑+导出区块（-120）、设置区块（-145）、视图/分屏区块（-150）、SelectionClearFilter（-85）、UI 组装（-110），动作均为控制器一行委托。
- 可单测控制器 5 个 + 独立 QObject 1 个：`EditActionController` / `ExportActionController` / `SettingsActionController` / `ViewCoordinator` / `MainWindowUIBuilder` / `SelectionClearFilter`。
- 明确保留不拆的职责块（详见《Wave3剩余分支重构方案.md》第 6 节）：信号回调群、两阶段关闭流程、会话恢复协调、拖放处理、命令面板、插件回调等。

**定时器**（由 `TimerManager` 管理）：

- `auto_save_timer`（默认30秒）→ 调用 `save_all_to_temp()`
- `stats_timer`（500ms）→ 更新状态栏和资源栏统计
- `idle_reward_timer`（60秒）→ 在线挂机资源发放

**挂机机制**（由 `GameEngine` 计算）：

- **在线**：每分钟 fuel/ammo/steel +5，bauxite 每3分钟+5（用 `bauxite_counter` 计数）
- **离线**：启动时 `GameEngine.calculate_offline_reward()` 根据 `last_login` 计算时间差，收益 = 在线的 1/3（向大取整），上限24h，最少5分钟

**窗口启动与会话恢复**：

- `present()` — 统一的窗口显示入口（替代直接 `show()`）。`__init__()` 期间窗口始终不可见，最大化场景使用 `showMaximized()` 让 Qt 以最终尺寸完成首次渲染，避免普通尺寸→最大化尺寸的两段式跳变
- `_restore_window_geometry()` — 在窗口不可见状态下恢复几何和最大化状态。最大化场景预缩放控件树到屏幕可用尺寸，消除首帧 paint 时的视觉撕裂
- 会话恢复逻辑已提取到 `core/session_restore_service.py`（hotfix 阶段 3），`MainWindow` 只保留调用与 UI 提示：
  - `build_restore_plan(open_files)` — 恢复计划：`pre_show_entries`（首个标签 + 首个 Markdown 标签，若同一文件只恢复一次）在窗口显示前同步挂载；`deferred_entries` 显示后经 `QTimer.singleShot(0, ...)` 异步恢复
  - `restore_session(editor_tabs)` — 执行恢复，返回是否还有待打开文件（有则继续调度 `open_next_pending`）
  - `check_crash_recovery()` / `restore_after_crash(editor_tabs, session, session_manager)` — 崩溃恢复公开接口（安全拒绝跳过 + new 文件跳过）
  - `_restore_cursor` — 光标/滚动位置恢复，支持 `Editor` 与 `MarkdownPreviewWidget`；滚动仅在 `scroll_pos > 0` 时延迟设置，避免 0 值定时器在控件销毁后触发
- `FileActionController`（`editor/file_action_controller.py`，hotfix 阶段 4）— 文件打开编排：`open_file()`（安全校验 → 外部文件注册 → 最近文件）、`show_open_dialog()`、`refresh_recent_files()`（过滤已不存在的路径并持久化）。UI 副作用（错误弹窗/文件树刷新/菜单构建）保留在 MainWindow
- 关闭标签页位置记忆（`closed_tabs_memory`，workspace.json）：关闭标签时持久化光标/滚动位置（`WorkspaceStore`），重新打开时恢复并清除；Ctrl+Shift+T 内存栈限 50 条
- `webview2_runtime.log_availability()` — `main.py` 在主窗口创建前调用，只读注册表检测系统 WebView2 Runtime 并返回是否可用；缺失时记录 error 日志，窗口显示后弹一次可见提示（`INSTALL_HINT`）。WebView2 后端不再需要 WebEngine 时代的启动锚点与预热：`WebView2PreviewAdapter` 在构造期即把 controller 创建协程投递到事件循环，循环由 `main.py` 的 `qasync.QEventLoop` 提供（见 4.5）

### 4.3 编辑器 (`editor/editor.py`)

基于 `QPlainTextEdit`，使用 Mixin 模式组合功能。类继承：`Editor(AutoPairHandlerMixin, EditorActionsMixin, QPlainTextEdit)`

| 模块                              | 职责                                                                                            |
| --------------------------------- | ----------------------------------------------------------------------------------------------- |
| `editor/editor.py`                | 核心编辑器（行号、缩略图、语法高亮、自动缩进、虚拟滚动、粘贴检测）                              |
| `editor/editor_actions.py`        | 行操作、大小写转换、JSON/XML 格式化（Mixin）                                                    |
| `editor/auto_pair_handler.py`     | 括号/引号自动配对（Mixin，frozenset O(1) 过滤）                                                 |
| `editor/bracket_matcher.py`       | 括号匹配高亮（纯函数，扫描配对位置，支持中英文括号）                                            |
| `editor/indentation.py`           | 缩进统一入口（缩进宽度/缩进文本，禁止硬编码）                                                   |
| `editor/eol_utils.py`             | 行尾探测与规范化纯函数（LF/CRLF/CR）                                                            |
| `editor/text_stats.py`            | 文本统计纯函数（CJK 按字计数 + 拉丁按词计数）                                                   |
| `editor/folding.py`               | 折叠管理器（Markdown 标题折叠 + 代码缩进折叠）                                                  |
| `editor/outline_parser.py`        | Markdown 标题解析器（纯函数，提取标题层级与行号）                                               |
| `editor/outline_panel.py`         | Markdown 大纲导航面板（QTreeWidget 展示标题树）                                                 |
| `editor/completion.py`            | 文档缓冲区自动补全（词频匹配 + IME 组字期间不弹出）                                             |
| `editor/find_in_files_service.py` | 跨文件搜索后台服务（QThread 遍历 + 正则/纯文本匹配）                                            |
| `editor/find_in_files_panel.py`   | 跨文件搜索结果面板（按文件分组 + 双击跳转）                                                     |
| `editor/save_task.py`             | 后台文件保存任务（SaveTask + QThreadPool 异步写入）                                             |
| `editor/virtual_scroll.py`        | 延迟高亮管理器（大文件延迟语法高亮；Wave 4 E2 起为 Document 级多 View 协作，visibleRanges = ∪） |

主要功能块：

| 功能区       | 说明                                                                                                    |
| ------------ | ------------------------------------------------------------------------------------------------------- |
| **行号**     | `LineNumberArea` 子控件，重写 `paintEvent` 绘制行号，动态计算宽度                                       |
| **缩略图**   | 内嵌 `MinimapWidget`，通过 `_update_child_geometries()` 管理几何位置                                    |
| **语法高亮** | 调用 `get_highlighter_for_file()` 工厂函数，支持 Pygments 和内置 Markdown                               |
| **自动缩进** | `_handle_enter()` 保持缩进 + 检测 `:`/`{` 等触发额外缩进                                                |
| **虚拟滚动** | `VirtualScrollManager` 管理大文件延迟语法高亮                                                           |
| **行操作**   | `EditorActionsMixin`：删除行 / 复制行 / 上下移动行，通过 `beginEditBlock/endEditBlock` 保证 undo 原子性 |
| **大小写**   | `EditorActionsMixin`：`toggle_case` / `to_uppercase` / `to_lowercase` / `to_titlecase`                  |
| **格式化**   | `EditorActionsMixin`：JSON (`json.dumps`) 和 XML (`minidom.toprettyxml`) 格式化                         |
| **括号配对** | `AutoPairHandlerMixin`：`keyPressEvent` + `inputMethodEvent` 双路径处理英文和中文 IME 输入              |
| **右键菜单** | 全中文化菜单，包含大小写子菜单和格式化选项                                                              |

**括号配对的复杂性**：

- 支持英文 `() [] {} "" ''` 和中文 `（）【】「」『』《》〈〉""''`
- `keyPressEvent` 处理英文键盘直接输入
- `inputMethodEvent` 处理中文 IME 提交的字符
- 智能判断：左右均有非空白字符且不是已有配对 → 不配对
- 嵌套输入：已有配对符号之间输入新配对符号 → 正常补全
- 引号智能：通过 `_pick_single_cjk_quote()` 用未闭合引号栈判断应插入左/右引号
- Backspace 成对删除；选中文本时自动包裹

**排版设置（代码字体 / 正文行距 / 代码块行距）**：

三个设置项各有唯一读取入口（`Config.get_code_font_family()` / `get_line_spacing()` /
`get_code_line_spacing()`，转发到 `SettingsStore`），调用方不得直接读 `get_editor_setting()`：

| 设置项                     | 默认        | 作用范围                               |
| -------------------------- | ----------- | -------------------------------------- |
| `editor.code_font_family`  | Courier New | 编辑器代码块 / 预览代码块 / 导出代码块 |
| `editor.line_spacing`      | 1.5         | 编辑器正文 + 预览 + 导出               |
| `editor.code_line_spacing` | 1.35        | 预览 + 导出（编辑器内不区分，见下）    |

- 读取处兜底：非法值回退默认，越界夹取到 `LINE_SPACING_MIN`~`LINE_SPACING_MAX`（0.5~5.0）。该区间同时是 `config_import_service` 的校验区间与设置对话框 `QDoubleSpinBox` 的区间——三者同源，避免「导入合法值被界面静默夹掉」
- **编辑器侧**（`Editor.set_line_spacing()`）：Qt 以 `QTextBlockFormat` 的线高**百分比**（`ProportionalHeight`，即倍数 ×100）表达行距，与预览 CSS 的 `line-height` 语义相近但不完全等价（编辑器字号可调、预览代码块字号固定 14px，同一数字视觉松紧会有细微差异）。逐项接线：设置变更走 `EditorTabs.set_line_spacing_all()`；行距是**按块**存储的格式，整篇替换文本（`setPlainText` 覆写 / `load_content`）与共享文档 attach/detach 后都必须重新应用
- 编辑器**内**正文与代码块不区分：同一文本流按块切分代码块代价过高，故 `code_line_spacing` 只作用于预览与导出
- **`mergeBlockFormat` 会被 Qt 记为一次编辑**（进撤销栈并置 `isModified`），而行距是显示属性而非内容改动——应用后必须还原两项：脏标记不还原会出现「打开文件即变脏」与「关标签页误弹保存确认」；撤销栈不还原会出现「刚打开的文件就可撤销」，用户第一次 Ctrl+Z 只会把行距悄悄改回默认。仅当文档本来就没有任何历史（撤销与重做都为空）时才清掉这一条，已有历史时保留（清栈会连带丢掉用户自己的重做记录）
- **预览 / 导出**：`_preview_css_vars()` 与 `build_export_html_document()` 分别把两个倍数注入 `--line-spacing` / `--code-line-spacing`（无单位数字，带单位会污染 `line-height` 与 `calc()`），由 `MARKDOWN_LAYOUT_CSS` 的代码块规则与导出外壳的 `body` 规则分别取用——预览与导出共用同一份排版 CSS，不会漂移
- 导出侧接线必须**整体**传参：`ExportActionController._typography()` 一次读出「代码字体 / 正文行距 / 代码块行距」三项并展开给 `ExportService`。`build_export_html_document()` 的默认参数只是兜底，漏传不会报错、只会静默回落默认倍数（曾因此出现「预览改了行距、导出纹丝不动」）；「另存为 PDF / HTML」路径（`EditorTabs._save_as_pdf()` / `_save_as_html()`）逐项传同样三项，两条链路语义一致
- 两侧行距可比的前提是**字号基准一致**：行距是无单位倍数，像素行距 = 倍数 × 自身 font-size。预览模板 `body` 为 14px，导出外壳 `body` 同样显式声明 `font-size: 14px`（此前缺省落到浏览器默认 16px，同一倍数在两侧换算出的像素行距不同）。预览代码块字号固定 14px，导出代码块继承同一基准

### 4.4 标签页管理 (`editor/editor_tabs.py`)

| 组件              | 说明                                                                                                                                                                                                           |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DraggableTabBar` | 继承 `QTabBar`，标签内拖拽 = 重排序，拖出标签栏 = 发起 `QDrag`（携带文件路径 MIME）                                                                                                                            |
| `EditorTabWidget` | 继承 `QTabWidget`，配合 `SharedDocument`/`ViewState`（`core/shared_document.py`）管理标签状态（3.5.8 起：内容/编码/eol/dirty/折叠/书签单一源在 Document；Wave 4 D：TabState 已淘汰，`document_model.py` 删除） |
| `SaveAsDialog`    | 自定义另存为对话框，支持编码选择（UTF-8/GBK/UTF-16）                                                                                                                                                           |

**核心逻辑**：

- `open_file()` — 编码级联检测（UTF-8 → GBK → UTF-16 → 容错UTF-8），Markdown 文件自动使用 `MarkdownPreviewWidget`；新增 `render_preview` 参数（默认 `True`），设为 `False` 时延迟预览渲染以加速启动恢复；3.5.8：另一面板已打开同一文件时经 `DocumentRegistry.get_by_path` 命中共享 Document，直接新建 View attach（不重新读盘）
- `_on_text_changed()` — 比较当前内容与 `last_saved_content`，决定是否标记为已修改（标签名加 ` *`）；粘贴操作不计入打字奖励
- `move_file_to_folder()` — 先保存最新内容 → `shutil.move` → 更新 Document 的 filepath（`DocumentRegistry.move_path` re-key + `bind_path` 广播，所有 View 路径/标题同步），移动前检查目标路径未被其它 Document 占用
- 保存状态副作用集中在 Document：`_on_save_state_changed(tab_id, state_name)` 的 CLEAN 分支统一处理 `mark_saved()` / `mark_new_saved()`
- 所有编辑操作（undo/redo/cut/copy/paste/行操作/大小写/格式化）通过代理方法转发给当前编辑器
- 3.5.8：每个 View 持有 `shared_doc` 与 `DocumentViewBinding`（`_connect_doc_binding`），dirtyChanged → 标题脏标记、nameChanged → 标题跟随、pathChanged → 共享 Document 路径 + Markdown 预览基准跟随；关闭/迁移前 `_disconnect_doc_binding` 断开；共享 Document 以 Document 侧 `dirty` 为单一源（save_all / save_all_for_close / get_unsaved_tab_infos / 关闭判定同规则）

### 4.5 Markdown 预览 (`editor/markdown_preview.py`)

**渲染路径与样式单一来源（Wave 1.5）**：

- 主渲染路径为 `markdown_preview.py`（markdown-it-py，含源码行号注入 / 异步高亮 / 本地图片解析），渲染显示唯一路径为 WebView2（后端经 `web_preview.create_preview_adapter()` 取得；Qt WebEngine 后端与 QTextBrowser 回退均已删除）；`secure_markdown_renderer.py` 为统一安全渲染与 HTML/PDF 导出入口（`render_markdown_to_safe_html` / `build_export_html_document`），兼作 `strip_dangerous_html` 清洗来源，非遗留渲染器。
- 预览模板 `PREVIEW_HTML_TEMPLATE` 与导出文档共用 `secure_markdown_renderer.MARKDOWN_LAYOUT_CSS` 内容排版（单一来源），颜色经 CSS 变量由各端从主题 token 注入；文档外壳（body）与预览交互样式（TOC / 代码块容器 / 复制按钮 / 折叠 / 滚动条）保留各端局部。
- fenced code 的识别与语言提取同样是单一来源：`secure_markdown_renderer.CODEBLOCK_RE` 与 `extract_language_from_code_attrs`（认 `language-` 与 `lang-` 两种 class 前缀），预览侧 `markdown_preview` 以 `_CODEBLOCK_RE` / `_extract_language_from_code_attrs` 导入复用，避免两处各留一份正则。
- 导出渲染的代码高亮经 `render_markdown_to_safe_html(content, highlight)` 注入回调（`ExportService._code_highlighter` → `highlight_code_html`），与预览同源；导出配色固定解析亮色变体（`v2_export_variant_id`），`render_content` / `export_html` / `export_pdf` 的 `theme_engine` 为**必填**，不提供「无主题引擎则退化为纯文本代码块」的降级路径。

**渲染管线**：

```
编辑器文本 → markdown 库渲染 HTML → _process_code_blocks()（Pygments 内联样式高亮 + 浅蓝容器 + Unicode 标记）
           → _resolve_local_images()（相对路径 → file:// 绝对路径）
           → PREVIEW_HTML_TEMPLATE 包裹 → Web Preview Adapter（WebView2）显示
```

**异步渲染管线**（Feature Flag `async_highlight` 控制）：

```
编辑器文本 → markdown 库渲染 HTML → _process_code_blocks_async()（代码块先用纯文本占位）
           → AsyncHighlightRenderer 后台线程渲染代码高亮
           → _on_async_highlight_done() 信号回调替换占位符为高亮结果
```

**增量渲染**（Feature Flag `markdown_incremental` 控制）：

- `IncrementalRenderer` 基于文本 MD5 哈希缓存渲染结果，相同文本直接返回缓存（全文级缓存，非行级增量）
- **HTML render cache**（Wave 4 C）：`document_render_cache.py` 以 Document 为键缓存最终 HTML，Document 改动渲染一次、多 View 共用（revision 单调递增作为缓存键）；分屏多 View 场景避免每次编辑各自全量重渲染

**浮动复制按钮**（WebView2 单路径后）：

- 代码块容器 `.code-container` 内嵌 `<button class="code-copy-btn" data-code-index="N">`，由 CSS `.code-container:hover .code-copy-btn` 控制悬停显示；单路径化后不再需要 `QTextDocument` 命中测试与 `mouseMoveEvent` 判定
- 点击由预览页内 JS 捕获（`e.target.closest('.code-copy-btn')`），经 `window.pnPostMessage('__pncopy__:N')` 回传索引；页面与宿主之间走 WebView2 官方消息通道（`chrome.webview.postMessage` → `add_web_message_received`），Python 侧经适配器 `message_received` 信号（`markdown_preview._on_preview_message`）接收并按索引取源码执行复制，并临时把按钮文案换成 ✔ 作为反馈
- 复制源码由 Python 侧 `self._code_blocks[index]` 提供，不依赖渲染后的 DOM；QTextBrowser 时代用于 `QTextDocument.find()` 定位的一对不可见占位标记（`⌜N⌝ / ⌞N⌟`）及 `.code-marker` 样式已随单路径化删除（A 分支仍在用，其测试以 `@a_only` 门控在 B 上跳过）

**源码行号同步**：

- `_render_markdown_with_source_map()`：使用 `markdown-it-py` 的 `token.map` 给块级节点注入 `data-source-line` 属性（1-based 行号），覆盖 heading_open/paragraph_open/blockquote_open/bullet_list_open/ordered_list_open/list_item_open/table_open/thead_open/tbody_open/tr_open/hr/fence/code_block 共 13 种 token
- `_build_container()` 支持 `source_line` 参数：代码块外层容器携带 `data-source-line` 属性
- `_current_editor_top_line()`：通过 `cursorForPosition(QPoint(0, 0))` 获取编辑器视口顶部行号
- `_sync_scroll()` 改为源码行号同步：经适配器 `run_javascript`（WebView2 侧为 `execute_script_async`）调用 `scrollToSourceLine(line)`（唯一同步路径）
- HTML 模板注入 `scrollToSourceLine()` JS 函数：查找 `data-source-line` 节点，在相邻锚点间线性插值计算滚动位置
- HTML 模板注入 `resyncAfterImagesLoaded()` JS 函数：图片 load/error 事件触发后重新同步预览位置（内部复用 `resyncAfterLayout()`；数学公式与图表渲染完成后同样调用它——两者都会改变节点高度，不重算锚点缓存与滚动位置就会停在错位置）

**预览增量更新**：

- `PREVIEW_HTML_TEMPLATE` 包含 `<div id="content">` 包裹内容区
- 首次渲染经适配器 `set_html` 整页加载模板，`load_finished` 信号触发后标记 `_html_template_loaded = True`
- 后续渲染经适配器 `run_javascript()` 仅更新 `document.getElementById('content').innerHTML`
- 切换文档（`base_path` 变化）时自动重置标志，强制下次全量加载

**主题切换就地更新**：

- `_preview_css_vars()` 是预览 CSS 变量的单一真相源（首屏模板注入与运行时更新同源），首屏经 `_build_preview_css_vars()` 写入 `--css-*` 变量
- 模板已加载时，主题/排版（代码字体、正文行距、代码块行距）变更经适配器 `run_javascript(_css_vars_update_js(...))` 就地改写 `:root` CSS 变量，不再整页 `set_html` 重载（避免切换闪烁）；模板未加载则随首屏整页加载一并灌入

**首次渲染稳定化**：

- 新增 `refresh_preview_now()`，Markdown 文件 `set_base_path()` 后显式触发 `_update_preview()`，不再依赖 `textChanged` 防抖定时器

**非活动预览延迟渲染**：

- 新增 `_preview_dirty` / `_initial_preview_rendered` 标志，`open_file(render_preview=False)` 打开的 Markdown 标签延迟预览渲染
- `invalidate_preview()` — 将预览标记为脏，下次激活时重新渲染
- `ensure_preview_rendered()` — 仅在 `_preview_dirty` 时触发渲染，避免重复计算。选项卡切换时被调用，确保切换到该标签时预览已就绪
- 启动恢复时首个标签以外的 Markdown 文件均以 `render_preview=False` 打开，加速启动

**WebView2 后端集成**：

- `MarkdownPreviewWidget` 经 `create_preview_adapter()` 构造 WebView2 后端（无 `webengine_runtime` 参数、无启动锚点）
- 加载：`set_html` → `navigate_to_string`（后端按需注入资源根 `<base href>`）；资源根：`set_resource_root` → `set_virtual_host_name_to_folder_mapping`；显示控制：`controller.is_visible`
- 加载完成：`NavigationCompleted` 事件 → 适配器 `load_finished` 信号；页面 → Python 消息：`chrome.webview.postMessage` → `add_web_message_received` → `message_received`（协议为 `<前缀>:<载荷>`，前缀见预览模板的 `window.pnPostMessage`；**不依赖 `document.title`**）
- PDF 导出：`export_pdf` → `print_to_pdf_async`（临时文件中转后回传 bytes；`should_print_backgrounds = True` 对齐 WebEngine 的默认打印背景，否则代码块底色整片丢失）
- 后端失败不可见即无效：Runtime 缺失或初始化异常时转入失败态，在预览区显示可读提示（`INSTALL_HINT` 或异常文案），不留空白
- **释放职责（谁在什么时机关 controller）**：`close()` 是通用 teardown（幂等：摘除事件处理器 → 释放 controller → 兑掉排队导出）——「一次性」语义只属于 `export_pdf`。三条释放路径：① `MarkdownPreviewWidget` 关闭/析构时 `shutdown_preview()`；② 关闭 Markdown 标签页时 `EditorTabs` 触发同一调用（QTabWidget 不删除页面控件，不能指望父子链）；③ 退出序列在控件树析构**之前**经 `MainWindow.shutdown_previews()` 统一关闭全部面板的预览（`_finalize_close` 与 `main.py` 各一处，顺序在 `window.deleteLater()` 之前）。PyWinRT 绑定导入失败时 `create_preview_adapter()` 返回降级适配器（显示安装指引 + 原因，导出走失败回调），启动不因绑定损坏而崩溃
- **同步接口防护**：`set_html` / `set_visible` / `set_resource_root` 内的 WinRT 调用全部包 try/except 转失败态（异常从 QTimer 槽逃逸在 PyQt6 下是 abort）；`_navigate` 前做体积判定（1.8 MB 阈值——`NavigateToString` 官方上限 2 MB，渲染产物是源码的数倍），超限给出可读提示。`load_finished` 只对本适配器经 `_navigate` 发起的导航发出（`_navigating` 归属标记），初始空白文档的完成事件不会误置「模板已加载」

**数学公式与图表（C4）**：

- **公式（KaTeX 0.18.7）**：语法在 **markdown 词法层**识别（`mdit_py_plugins.dollarmath`，定界符取 pandoc/GitHub 口径：开 `$` 后不接空白、闭 `$` 前不接空白且其后不接数字），不走「渲染后由 auto-render 扫 `$…$`」——后者会被 markdown 的转义与强调规则吃掉公式内容（`$a\,b$` → `a,b`、`$a*b$` → `a<em>b</em>`），且没有定界符规则，会把「价格 $5 与 $3」当成公式。注册点唯一：`math_render.register(md)`，预览与导出两个解析器共用；产物为 `<span class="math inline">` / `<div class="math block">`，样式与脚本由 `math_render` 提供（字体转 data URI，`lru_cache` 烘焙一次，仓库不落生成物）。
- **公式注入时机**：预览模板**始终内联一次**（模板只在首屏加载，之后仅换 `#content` 内容），并在每次内容更新后重跑渲染；导出文档按 `has_math()` **按需内联**，无公式的文档不背约 645 KB。
- **图表（Mermaid 12.0.0）**：围栏在渲染阶段经 `secure_markdown_renderer.extract_mermaid_blocks()` 转成容器 div，class 用**私有 `pn-mermaid`** 而非 mermaid 约定的 `mermaid`（库自带「文档就绪后自动渲染所有 `.mermaid`」，会与我们由 Python 控制渲染时机的模型撞车）。转换必须早于代码块处理，否则图表会占掉代码块序号（复制按钮索引）并被高亮器处理。
- **图表资产三条加载路径**：预览**懒注入**（首次出现围栏才 `run_javascript` 注入 vendor，`_mermaid_loaded` 随整页重载失效）；HTML 导出**按需内联**（写盘文件由用户浏览器打开，不经 `NavigateToString`，保持单文件自包含）；PDF 导出**外置注入**（`NavigateToString` 对文档有 2 MB 上限，内联 5.6 MB 会以 E_INVALIDARG 失败；文档只声明 `<meta name="pn-mermaid-vendor" content="external">`，由适配器经 `add_script_to_execute_on_document_created_async` 注入）。
- **异步就绪门**：Mermaid 渲染是异步的，`NavigationCompleted` 只代表装载完成。导出文档带 `<meta name="pn-async">`，页面渲染结束经 `chrome.webview.postMessage` 回传 `mermaid_render.READY_MESSAGE`（适配器 `_on_web_message` 消费，不冒泡给预览）；`_print_current` 在导航之后轮询该标志再打印（8s 超时降级打印并告警）。用轮询而非 `asyncio.Event`：消息回调不保证在事件循环线程上触发。
- **打印视口**：按容器宽度计算自身宽度的图表（Mermaid 甘特图取 `parentElement.offsetWidth`）在从不进入布局的离屏容器里会失准，导出后挤在纸面左侧一小条。故 `_export_async` 打印前把视口调整为纸面内容框尺寸（`page_width - 左右边距`，1in = 96 CSS px）。
- **资源与许可**：`data/assets/vendor/{katex,mermaid}/` 随包分发（`PanzerNote.spec` 的 `datas=[('data','data')]` 整体收集，无需额外打包改动），登记于 [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md)。

### 4.6 代码高亮主题 (`editor/highlight_themes.py`)

- **颜色来源统一**：所有语法高亮颜色从 v2 syntax palette（`themes/syntax/palettes/*.json` + 变体 override）读取，经 `v2_syntax_colors()` 消费，不再保留独立的 `THEMES` 字典
- **`TOKEN_MAP` 映射表**：60+ 条 `{Pygments Token → syntax_* token}` 映射，覆盖 Keyword/Name/Literal/Comment/Operator/Punctuation/Text/Error/Generic 等所有 Pygments token 层级
- **跨主题装饰**：`_TOKEN_BOLD` / `_TOKEN_ITALIC` frozenset 统一管理粗体/斜体装饰，不随主题切换变化
- **编辑器端**：`get_editor_formats(theme_engine)` → 经 `v2_syntax_colors()` 动态构建 `{Token: QTextCharFormat}`
- **预览/导出端**：`highlight_code_html(code, language, theme_engine)` → 从主题颜色生成 Pygments style class，输出内联样式 HTML（预览与 PDF 导出共用）
- 切换主题时语法高亮颜色无需任何额外处理——manager `theme_committed` 信号触发订阅组件经 v2 token 重读，颜色自动跟随（详见 [color_audit.md](theme-design/color_audit.md)）

### 4.7 小秘书 (`game/secretary_widget.py`)

- 固定在 `editor_container` 右下角（通过 `eventFilter` 监听父容器 `Resize`/`Move` 事件）
- 防抖机制：位置更新请求通过 `_position_timer`（≤50ms 间隔）合并，避免频繁重绘
- 动态位置计算：`_calculate_target_position()` 基于 margin 值，确保立绘右下对齐且不越界
- 百分比尺寸控制：`_apply_size()` 根据父容器面积和 `size_percent`（默认 7%，范围 3%~20%）动态计算宽高，保持 210:380 宽高比
- `set_size_percent(percent)` / `get_size_percent()` — 运行时调节尺寸，自动持久化到 `settings.json`
- 窗口 resize 时自动重新计算尺寸和位置
- 台词系统：`secretary_lines.json` 定义多种事件（启动/保存/建造/闲置/点击等），支持 `{nickname}` 和 `{self}` 占位符
- 立绘加载：按 `character_id/character_name/skin_name/state` 构建路径，fallback 到 `secretary.png`

### 4.8 高 DPI 缩放 (`utils/dpi_helper.py`)

- `init_dpi(app)` — 检测 `Qt.AA_EnableHighDpiScaling` 是否已启用：
  - 若已启用：`scale_factor = 1.0`（Qt 自动处理 DPI 缩放，dpi_helper 所有 scale 函数为 no-op）
  - 若未启用：基于 `logicalDotsPerInch` / `devicePixelRatio` 计算缩放因子
- **注意**：当前 `main.py` 已启用 `AA_EnableHighDpiScaling`，因此 dpi_helper 在生产环境中实际为 no-op
- `scale(value)` / `scale_stylesheet(css)`

### 4.9 快捷键管理 (`core/shortcut_manager.py`)

- `ShortcutManager(config)` — 管理所有快捷键的注册、冲突检测、自定义和持久化
- `register(action_id, name, default_shortcut, callback, category)` — 注册快捷键，返回 QAction
- `check_conflicts(key_sequence, exclude)` — 检测系统级（Ctrl+C/V 等）和应用内部冲突
- `set_shortcut(action_id, key_sequence)` — 修改快捷键并持久化到 `settings.json`
- `reset_shortcut(action_id)` / `reset_all()` — 恢复默认快捷键
- `get_categories()` / `get_all_shortcuts()` — 获取分类和完整列表
- `_normalize_key(key)` — 统一快捷键格式（小写 + 修饰键排序），用于冲突比较
- **注意**：ShortcutManager 已接入 MenuBuilder，所有菜单项通过 `manager.register()` 注册，自定义快捷键功能已生效

### 4.10 统一错误提示 (`utils/error_handler.py`)

- `ErrorCategory` 枚举：FILE / NETWORK / CONFIG / GAME / EDITOR / PERMISSION / MEMORY / GENERAL
- `ErrorHandler.show_error(category, title, message, suggestion, detail)` — 显示用户友好错误提示
- `ErrorHandler.show_from_exception(exception, category, title)` — 从异常对象生成提示
- `ErrorHandler.sanitize(text)` — 公共接口，过滤敏感信息（password/token/secret/api_key/key 自动脱敏）
- `_sanitize_message(text)` — 内部过滤函数，使用正则匹配：Windows/Unix/Mac 路径、Traceback、IP 地址、密码/Token/Key
- `_ErrorDialog` — 默认错误对话框，使用 QMessageBox，样式与应用统一
- 自定义处理器：`register_handler(category, handler)` / `unregister_handler(category)`，支持回退

### 4.11 安全模块 (`security/`)

阶段四新增的安全防护体系，包含六个核心模块，集成到 `config.py`、`editor_tabs.py`、`file_tree.py`、`find_replace.py`、`main_window.py` 中。

#### 4.11.1 路径安全验证 (`security/path_validator.py`)

- `PathValidator` — 路径安全验证器，提供白名单机制和目录穿越防护
- `normalize(path)` — 使用 `os.path.realpath` 规范化路径，处理 Windows `\\?\` 长路径前缀
- `add_allowed_root(root_path)` — 添加安全路径白名单（大小写不敏感）
- `is_path_safe(path)` — 综合安全检查：空值/类型/长度/穿越/白名单
- `validate_path(path)` — 验证并返回规范化路径，失败抛出 `PathSecurityError`/`PathTraversalError`/`PathNotInWhitelistError`
- `MAX_PATH_LENGTH = 260` — 路径长度上限

**安全异常层次**：

```
PathSecurityError (基类)
├── PathTraversalError    — 目录穿越攻击
└── PathNotInWhitelistError — 路径不在白名单
```

#### 4.11.2 文件操作安全控制 (`security/file_guard.py`)

- `FileGuard` — 文件操作安全守卫，集成路径验证、大小限制和超时控制
- `safe_read(filepath, encoding, validate_path)` — 安全读取文件
- `safe_read_bytes(filepath, validate_path)` — 安全读取二进制文件
- `safe_write(filepath, content, encoding, validate_path)` — 安全写入文件，自动创建目录
- `check_file_size(filepath)` — 检查文件大小是否超限
- `get_real_file_size(filepath)` — 获取真实文件大小（处理符号链接和稀疏文件）
- `DEFAULT_MAX_FILE_SIZE = 50MB` — 默认文件大小上限
- `DEFAULT_TIMEOUT = 30s` — 默认操作超时阈值
- 超时机制：使用 `threading.Thread(daemon=True)` 执行文件操作，`join(timeout)` 控制超时

**安全异常层次**：

```
FileSecurityError (基类)
├── FileSizeExceededError      — 文件大小超限
└── FileOperationTimeoutError  — 文件操作超时
```

#### 4.11.3 文件访问上下文 (`security/file_access_context.py`)

- `FileAccessContext` — 文件读写访问上下文枚举，替代模糊的 `validate_path=False`
- 枚举值：`USER_DOCUMENT_READ` / `USER_DOCUMENT_SAVE` / `TEMP_AUTOSAVE` / `INTERNAL_CONFIG` / `INTERNAL_SAVEGAME` / `PLUGIN_REQUEST` / `SESSION_RESTORE` / `SETTINGS_IMPORT` / `EXPORT_TARGET`
- 为每个文件操作提供明确的语义来源，配合 `FileOpenService` 和 `FileGuard` 实现来源感知的权限分级

#### 4.11.4 输入验证框架 (`security/input_validator.py`)

- `InputValidator` — 统一输入验证器，覆盖文件名、搜索内容、设置值
- `validate_filename(filename)` — 宽松文件名验证（允许空扩展名）
- `validate_filename_strict(filename)` — 严格文件名验证（不允许点号开头/结尾）
- `sanitize_filename(filename)` — 清洗文件名（替换非法字符为下划线，截断长度）
- `validate_search(query)` — 搜索内容验证（XSS/注入模式检测，长度限制 10,000）
- `validate_setting(key, value, expected_type, min_val, max_val, allowed_values, max_length)` — 设置值验证
- `MAX_FILENAME_LENGTH = 255` / `MAX_SEARCH_LENGTH = 10000` / `MAX_SETTING_STRING_LENGTH = 1000`

**文件名验证规则**：

- 非法字符正则：`[<>:"|?*\\/\x00-\x1f]`
- Windows 保留名称：`CON`/`PRN`/`AUX`/`NUL`/`COM1-9`/`LPT1-9`
- 路径注入模式：`../`/`..\\`/`\\`/`/`
- 严格模式额外限制：不允许以点号开头或结尾

**搜索内容危险模式**：

- `<script>` / `javascript:` / `vbscript:` — 脚本注入
- `on\w+=` — 事件处理器注入
- `data:text/html` — 数据 URI 注入

**安全异常层次**：

```
ValidationError (基类)
├── FilenameValidationError  — 文件名验证失败
├── SearchValidationError    — 搜索内容验证失败
└── SettingValidationError   — 设置值验证失败
```

#### 4.11.6 安全管理器 (`core/security_manager.py`)

从 `Config` 类中拆分出的安全功能集成管理器，将 `PathValidator`、`FileGuard`、`InputValidator` 统一封装。

- `SecurityManager(path_validator, file_guard, input_validator)` — 安全管理器
- `path_validator` / `file_guard` / `input_validator` — 三个安全组件的只读属性
- `add_allowed_root(root_path)` — 添加路径白名单根目录
- `validate_setting_value(key, value, expected_type, ...)` — 设置值验证（委托 InputValidator）

#### 4.11.7 安全模块集成点

| 集成文件                 | 集成方式                                                                                                                                  |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `core/config.py`         | 初始化 `SecurityManager`（内含 PathValidator/FileGuard/InputValidator）；所有 JSON 读写通过 `FileGuard`；设置值通过 `InputValidator` 验证 |
| `editor/editor_tabs.py`  | 文件打开通过 `FileGuard.safe_read()` 读取；处理 `FileSizeExceededError`/`FileOperationTimeoutError`                                       |
| `editor/file_tree.py`    | 新建文件/文件夹通过 `InputValidator.validate_filename_strict()` 验证；文件创建通过 `FileGuard.safe_write()`                               |
| `editor/find_replace.py` | 搜索内容通过 `InputValidator.validate_search()` 验证，拒绝注入模式                                                                        |
| `main_window.py`         | 拖放文件通过 `_SUPPORTED_DROP_EXTS` 白名单校验；PDF/HTML 导出均显式禁用 raw HTML                                                          |

#### 4.11.8 拖放文件类型白名单

`MainWindow` 类的 `_SUPPORTED_DROP_EXTS` 类属性（`frozenset`），在 `dropEvent` 中对拖入文件进行扩展名白名单校验。包含允许拖入打开的文件扩展名：`.txt`、`.md`、`.py`、`.c`、`.cpp`、`.h`、`.java`、`.js`、`.json`、`.html`、`.css`、`.xml`、`.yaml`、`.yml`、`.toml`、`.ini`、`.log`、`.sql`、`.sh`、`.go`、`.rs`、`''`（无扩展名）。

**安全意义**：防止用户意外将二进制文件拖入编辑器导致程序异常或显示乱码。

**扩展方式**：修改 `MainWindow._SUPPORTED_DROP_EXTS` 类属性即可，无需修改其他代码。

### 4.12 插件系统 (`plugins/`)

插件系统提供标准化的扩展机制，允许第三方开发者为应用添加功能。插件通过**能力声明（capabilities）** 与宿主交互：插件在 `plugin.json` 中声明所需能力，宿主按能力清单暴露受限 API。

> **⚠️ 可信插件模型声明**：当前插件系统是可信插件模型。插件代码运行在主程序进程中（GUI 线程），能力系统只限制 PanzerNote 暴露的 API 边界，不是完整安全沙箱。请只安装可信来源的插件。详细开发文档见 [../plugins/plugin_api.md](../plugins/plugin_api.md)。

#### 4.12.1 插件基类 (`plugins/plugin_base.py`)

- `PluginState` — 插件状态枚举（UNLOADED/LOADED/ACTIVATED/DEACTIVATED/ERROR）
- `PluginPermission` — 内部权限枚举（READ_SETTINGS/READ_SAVEGAME/READ_WORKSPACE/READ_FILE_TREE/OPEN_FILE/SHOW_MESSAGE/REGISTER_COMMAND/EDITOR_READ/EDITOR_WRITE/UI_NOTIFY/REGISTER_MENU/EVENT_SUBSCRIBE）
- `PluginMeta` — 插件元数据（name/version/description/author/min_app_version/**capabilities**/tags），`min_app_version` 默认值引用 `src.__version__`
- `PluginBase` — 插件基类，定义四个生命周期方法：`on_load(ctx)`/`on_activate()`/`on_deactivate()`/`on_unload()`（所有钩子在 GUI 线程执行）

**状态转换规则**：

```
UNLOADED → on_load() → LOADED → on_activate() → ACTIVATED
ACTIVATED → on_deactivate() → DEACTIVATED → on_activate() → ACTIVATED
ACTIVATED → on_deactivate() → DEACTIVATED → on_unload() → UNLOADED
LOADED → on_unload() → UNLOADED
任意状态 → 异常 → ERROR
```

#### 4.12.2 能力注册中心 (`plugins/capability_registry.py`)

能力系统采用"声明 → 映射"两层结构（Wave 5 D6）：

- `CAPABILITY_PERMISSIONS` — 能力 id → 内部权限映射（如 `editor.read_text` → `EDITOR_READ`）；`None` 表示无需权限（`app.version`）
- `BUILTIN_CAPABILITIES` — 内置能力（`data.read`/`data.write`），无需在 manifest 声明即可调用
- `CapabilityRegistry.register(cap_id, permission, impl, copy_result, pass_plugin_id)` — 宿主（MainWindow 等）注册能力实现；`pass_plugin_id=True` 时调用方插件 id 作为 impl 第一个参数（命名空间类能力隔离用）
- `CapabilityRegistry.authorize(plugin_id, capabilities)` — 插件加载时登记其声明的能力并换算权限
- `CapabilityRegistry.invoke(cap_id, plugin_id, *args)` — 检查声明（内置能力豁免）+ 权限 + 调用实现 + 返回值深拷贝
- 双层异常：`PluginCapabilityError`（能力不存在/未声明/事件白名单外/订阅超限）、`PluginPermissionError`（能力已知但授权不满足）

已注册能力清单（17 项：15 项需声明 + `data.read`/`data.write` 内置）见 [../plugins/plugin_api.md](../plugins/plugin_api.md) 能力清单。

#### 4.12.3 命名空间上下文 (`plugins/plugin_context.py`)

`on_load(ctx)` 接收的 `ctx` 是命名空间式 `PluginContext`（Wave 5 D4），插件**不直接持有** Config / SavegameManager / MainWindow 等内部对象：

- `ctx.app` — 应用信息（`app.version`）
- `ctx.settings` — 设置读取（`settings.read`：get/get_editor/get_game/get_secretary）
- `ctx.savegame` — 存档读取（`savegame.read`：resources/field）
- `ctx.workspace` — 工作区（`workspace.recent_files` / `workspace.open_file`）
- `ctx.file_tree` — 笔记库（`file_tree.read`：notebooks_path）
- `ctx.editor` — 编辑器（`editor.read_text`/`editor.selection.*`/`editor.read_path`）
- `ctx.ui` — UI 扩展（`ui.notify`/`ui.show_message`/`ui.register_command`/`ui.register_menu_item`）
- `ctx.data` — 插件私有数据（内置 `data.read`/`data.write`）
- `ctx.events` — 事件订阅（`event.subscribe`）

每次调用经 `CapabilityRegistry.invoke` 完成权限检查与深拷贝保护。

#### 4.12.4 插件事件总线 (`plugins/plugin_event_bus.py`)

`PluginEventBus`（Wave 5 Batch 4）承载插件事件订阅，复用 Qt 事件循环实现节流：

- 事件白名单 7 个：`document.opened`/`document.saved`/`document.closed`/`cursor.changed`/`content.changed`/`theme.changed`/`file_tree.changed`
- 高频事件（`cursor.changed`/`content.changed`）合并到 100ms 窗口派发，仅保留最新 payload（无状态节流，不做异常频发降级）
- 单插件单事件订阅数上限 5，超限抛 `PluginCapabilityError`
- 回调异常 → 仅 log，不自动禁插件
- 插件卸载/重载自动解绑全部订阅（`PluginManager` 持有总线引用）

宿主接线（MainWindow）：EditorTabWidget 的 `document_opened`/`document_closed`/`cursor_position_changed`、`_on_content_modified`、`_on_file_saved`、ThemeEngine 的 `theme_changed`、FileTreeWidget 的 `tree_changed`、move/copy 成功路径。

#### 4.12.5 插件管理器 (`plugins/plugin_manager.py`)

- `scan_plugins()` — 从 `plugins/` 目录递归扫描插件包（仅填 manifest 清单，启动阶段不加载）；检测残留启动 marker → 插件进入安全模式
- `load_plugin(name)` — 加载插件（导入入口类、构造 PluginMeta、`authorize(capabilities)`、装配 PluginContext、`on_load(ctx)`；on_load 前写入启动 marker；manifest 校验在扫描阶段完成）
- `activate_plugin(name)` / `deactivate_plugin(name)` — 激活/停用（on_activate 成功后清除启动 marker）
- `unload_plugin(name)` — 卸载（`on_unload()` + 自动解绑事件订阅 + 撤销授权 + 经 `add_unload_hook` 通知宿主清理插件注册的命令面板命令）
- `reload_plugin(name)` — 热加载（停用→卸载→清除模块缓存→重新加载→恢复状态）
- `activate_enabled_plugins()` — **启动延迟加载（Wave 5 D5）**：窗口显示后由 MainWindow 经 `QTimer.singleShot(0, ...)` 调用，自动加载并激活 `enabled=true` 且非安全模式的插件，单个失败不影响其余

**启动恢复 marker（Wave 5 D14）**：`on_load` 前写入、`on_activate` 成功后清除（存于用户数据目录 `data/plugin_startup/`）。残留 marker = 上次启动在启动阶段异常退出 → 该插件进入安全模式（`SAFE_MODE`，管理对话框显示 `[安全模式]`），下次启动跳过，需在插件管理中手动加载处理。普通异常（程序未崩溃）会清除 marker，下次启动可重试。

**插件清单 (`plugin.json`) 必需字段**：`name`/`version`/`entry`；能力声明用 `capabilities` 数组；`enabled`（可选，默认 true）控制启动时是否自动加载激活。

### 4.13 主题系统 (`themes/`)

#### 4.13.1 主题引擎 (`themes/theme_engine.py`)

- **Theme v2 唯一运行时**（Wave8 Batch C 后 v1 遗留类型/builtin 主题/外部主题/YAML/回退路径已删除）：
  初始化 default 主题包（`themes/default/`，含变体/recipe/design/icon 数据）与 Core Controls 组件库（`theme_v2/library.py`）
- **QSS 生成**：`generate_stylesheet()` 以当前激活 variant 为单一真相源——结构段消费
  variant semantic token，Core Controls 走组件库 recipe 解析，覆盖全部 UI 元素
  （QMainWindow/QMenuBar/QTab/QTreeView/QStatusBar/QLabel/QPushButton/QLineEdit/QGroupBox/QDialog 等），整段原子切换
- **主题持久化**：通过 `config.get_view_setting("theme", "default/light")` 恢复上次保存的主题
  （`package/variant` 语义；旧值 `light`/`dark` 读取时迁移为 default 包）
- **v2 加载失败 = 启动显式报错**：抛 `ThemeLoadError`，main.py 弹错误框后退出，永不静默回退
- 主题切换即时生效，无需重启

**v2 主题包结构**（`themes/default/`）：

- `theme.json` — 包清单（包名/渲染器/变体/recipe/design 契约）
- `variants/light.json` / `variants/dark.json` — 变体语义 token（UI 通用 11 + `editor_*`/`md_*`/`search_*` 专用）
- `recipes.json` — 组件视觉配方（button/tab/tree_item/group_box/dialog/scrollbar 等）
- `design.json` / `icons.json` / `motion.json` — 设计 token / 图标 / 动效
- `syntax/palettes/*.json` — 共享语法配色 palette（light-default-v1 / dark-default-v1）

#### 4.13.2 主题预览 (`themes/theme_preview.py`)

- `ThemePreviewDialog` — 主题预览对话框，接入 ThemeAwareMixin，深色样式已补齐
- 多包 + 变体浏览（B8）：扫描 `themes/*/theme.json` 列出包，按包加载变体
- 按 v2 token 分组展示色块：通用颜色 / 编辑器颜色 / UI 区域 / 搜索高亮 / 书签与折叠 / 代码块 / Markdown 高亮 等
- 应用切换经 `theme_applied(package_id, variant_id)` 走 Snapshot Overlay 过渡

#### 4.13.3 主题感知混入 (`themes/theme_aware_mixin.py`)

- `ThemeAwareMixin` — UI 组件继承后自动订阅 `ThemeManager.theme_committed` 信号（package/variant 语义）
- 组件实现 `_apply_theme_colors()` 更新自身样式（经 v2 token / consumer 辅助读取）
- 已集成组件涵盖：Editor、MarkdownPreviewWidget、EditorTabWidget、MinimapWidget、FileTreeWidget、FindReplaceBar、StatusBarWidget、SecretaryWidget、ResourceBar、GameSidebar、ShortcutPanel、ThemePreviewDialog、PluginManagerDialog、CompletionPopup 等

### 4.14 存档管理器 (`core/savegame_manager.py`)

从 `Config` 类中拆分出的独立存档管理模块，负责游戏存档的加载和保存。

- `SavegameManager(file_guard, gamedata_dir)` — 存档管理器
- `load()` — 从 `savegame.json` 加载存档
- `save()` — 保存存档，返回 `SavegameSaveResult` 枚举值
- `add_resource(key, amount)` / `get_resources()` — 资源 CRUD
- `check_daily_checkin()` — 每日签到检查，首次启动自动发放奖励（燃料/弹药/钢材/铝材各+100）
- `get_savegame_field(key, default)` / `set_savegame_field(key, value)` — 字段级读写 API，替代整档引用透传（hotfix 阶段 4）
- **防泄漏只读视图**：`data` 属性 / `get_savegame()` 通过 `MappingProxyType` 暴露只读存档视图；`get_resources()` 返回拷贝，调用方无法修改内部状态（hotfix 阶段 4）

**SavegameSaveResult 枚举**：

| 值             | 说明     |
| -------------- | -------- |
| `SUCCESS`      | 保存成功 |
| `WRITE_FAILED` | 写入失败 |

### 4.15 集中式版本管理

版本号以 `src/__init__.py` 中的 `__version__` 为唯一真相源（Single Source of Truth），所有模块和配置文件通过引用获取版本号，而非硬编码。

**版本传播链路**：

```
src/__init__.py (__version__ = "2.3.0")
  ├─→ main.py                    (from src import __version__)
  ├─→ src/main_window.py         (from . import __version__)
  ├─→ src/plugins/plugin_base.py (from .. import __version__ as _app_version)
  │     └─→ PluginMeta.min_app_version 默认值
  ├─→ plugins/hello_panzer/main.py  (from src import __version__ as _app_version)
  ├─→ plugins/word_counter/main.py  (from src import __version__ as _app_version)
  └─→ pyproject.toml            (dynamic = ["version"] + attr = "src.__version__")
```

**工具函数**：

- `get_version_tuple()` — 返回版本号元组，如 `(1, 8, 0)`

**版本一致性验证** (`scripts/verify_version.py`)，5 项检查：

1. `src/__init__.py` 版本格式（semver X.Y.Z）
2. `pyproject.toml` 动态版本配置（无静态 version 字段）
3. Python 文件中无硬编码应用版本号
4. 文档中非更新日志区域的版本号引用
5. 运行时版本一致性（`plugin_base._app_version` 与 `__version__` 匹配）

**启动时检查** (`main.py._verify_version_consistency()`)：应用启动时自动验证 `plugin_base._app_version` 与 `src.__version__` 一致性，不一致时记录 WARNING 日志。

**版本更新流程**：

1. 仅修改 `src/__init__.py` 中的 `__version__`
2. 运行 `python scripts/verify_version.py` 验证一致性
3. 手动同步 `README.md` / `docs/architecture.md` / `plugins/plugin_api.md` 中的版本号

### 4.16 共享文档多视图（3.5.8）

**三层模型**：`Document`（内容与持久化状态）↔ `View`（编辑器/预览，只 attach 不拥有）↔ `ViewState`（每 View 独立展示状态）。

| 模块                            | 职责                                                                                                                                                                                                                 |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `core/shared_document.py`       | `SharedDocument(QObject)` 拥有 `QTextDocument` 与保存状态（dirty/save_status/path/encoding/eol）；信号源直接监听共享 QTextDocument 再统一转发；`ViewState`（cursor/scroll 快照）、`SaveSnapshot`（异步保存内容快照） |
| `core/document_registry.py`     | 全局注册表：`documents_by_id` / `path_index`（canonical 路径 → doc_id）/ `pending_path_index`（Save As 预留）/ `views`（doc_id → View 列表）；`release()` 仅最后一个 View 关闭时销毁 Document                        |
| `core/document_view_binding.py` | 每 View 一个信号接线器：`bind(signal_name, slot)` 登记 → `attach()`/`detach()` 幂等建立/断开；防裸 lambda 无人持有连接                                                                                               |

**关键机制**：

- **自动共享**（规格 2.1）：`open_file` 先查 `DocumentRegistry.get_by_path`，命中则 `_create_shared_view` 直接 attach（内容/编码/eol 单一源，不重复读盘）；面板内同 Document 至多一个 View
- **关闭决策树**（规格 2.3）：非最后 View → 直接关（不弹确认、不销毁 Document、不动未命名编号）；最后 View → dirty 确认 → `release()`（含未命名编号归还与 path_index 清理）
- **路径 re-key**（规格 2.2）：Save As 走 `reserve_path`（pending 预留）→ 成功后 `commit_path`（pending → path_index + `bind_path` 广播 pathChanged/nameChanged）；文件树移动走 `move_path`（直接换键，无 pending）；目标路径被其它 Document 占用一律拒绝
- **保存竞态防护**（规格 2.4）：`SaveTaskManager` 按 `(tab_id × save_status)` 两维度管理（面板内）；`SharedDocument.request_save()`/`on_save_succeeded()`/`on_save_failed()` 接线为**跨面板唯一门闩**——主面板与分屏的 Manager 相互独立，`document_key` 合并仅面板内有效，门闩保证同一 Document 全局同时最多一个实际写盘任务（最新内容必然最后落盘），保存完成直接连 `SaveTask.signals.finished` 释放（标签已注销也不卡死）；`safe_write` 原子化（同目录临时文件 + os.replace），并发写目标始终是完整版本
- **状态收敛 Document 级**：折叠（2.10）与书签（2.12）随 Document 共享；`dirty` 单一源在 Document，各 View 标题经 dirtyChanged 同步（`_on_view_dirty`）
  > **Known limitation / Future research**：每 View 独立折叠未实现——`FoldingManager` 通过 `QTextBlock.setVisible` 落状态于共享 QTextDocument 的 QTextBlock 上，View 级边界在 Qt 当前实现下不成立（规格 2.10 已核查）。当前行为：View A 折叠 → View B 同步折叠。实现每 View 独立折叠需重写呈现机制（per-view layout / paint），留作未来独立增强。
- **高亮**：两种高亮器（Markdown / Pygments）均实现 `set_dark_mode`，主题切换不经过 `set_file_type`（避免重建时摘除共享高亮）；关闭最后 View 前 `_detach_shared_from_widget` + release，杜绝悬垂引用（C++ deleted 崩溃）
- **lazy 高亮 Document 级协作**（Wave 4 E2）：`LazyHighlightManager` 由 per-View 改为 Document 级——同 Document 共享一个 coordinator，可视区高亮范围取各 View 的并集 `visibleRanges(Document) = range(View A) ∪ range(View B)`；滚动事件按 View 上报、coordinator 聚合调度，与 Document 级共享 highlighter 协作；仅大文件（≥1 万行）且 `large_file_mode` 激活时启用（E3/E4，flag 默认 False，运行时按需激活，无全局残留）
- **未保存聚合**：`get_unsaved_tab_infos` 返回含 `document_id`，`MainWindow.closeEvent` 按 document_id 跨面板去重（同一共享文件只列一次）；`save_all_for_close` 以 Document 侧 dirty 为准

---

## 5. 数据文件详解

### 5.1 `characters.json` — 角色数据库

当前包含 10 个示例角色。每个角色结构：

```json
{
  "id": "char_001",
  "name": "虎王",
  "name_en": "Tiger II",
  "type": "heavy", // light/medium/heavy/super_heavy/td/spg
  "nation": "G", // G=德/S=苏/U=美/E=英/J=日/F=法/C=中/I=意
  "rarity": 5, // 1普通~6神话
  "build_time_minutes": 300,
  "threshold": {
    "total": 1800, // 四资源总投入最低门槛
    "fuel": 500, // 各项最低门槛（可选）
    "steel": 800,
    "bauxite": 200 // 某些特殊角色需要铝材门槛
  },
  "portrait": "...",
  "voice_intro": "..."
}
```

同时定义了 `types`（6种车型）、`nations`（8国）、`rarities`（6级稀有度 + 颜色）。

### 5.2 `savegame.json` — 游戏存档

```json
{
  "resources": { "fuel": 3000, "ammo": 3000, "steel": 3000, "bauxite": 1000 },
  "cores": 0,
  "last_login": "2025-01-01T12:00:00",
  "today_date": "2025-01-01",
  "today_chars_typed": 0,
  "total_chars_typed": 0,
  "total_documents": 0,
  "construction_queue": [], // 规划：建造队列
  "owned_characters": {}, // 规划：已拥有角色 {id: {count, first_obtained, ...}}
  "achievements": [] // 规划：成就系统
}
```

### 5.3 `settings.json` — 用户设置

分六个命名空间：`editor`（编辑器）、`game`（游戏）、`secretary`（小秘书）、`view`（视图）、`window`（窗口几何）、`shortcuts`（快捷键自定义）。所有设置都有 `DEFAULT_SETTINGS` 兜底默认值。

`shortcuts` 段示例：

```json
{
  "shortcuts": {
    "file.new": "Ctrl+N",
    "file.open": "Ctrl+O",
    "file.save": "Ctrl+S"
  }
}
```

仅保存用户自定义的快捷键覆盖，未修改的使用 `_DEFAULT_SHORTCUTS` 中的默认值。

---

## 6. 信号/事件流

### 6.1 文件打开流

```
用户双击文件树 / Ctrl+O
  → FileTreeWidget.file_open_requested(filepath)
  → MainWindow._open_file(filepath)
     → FileActionController.open_file(filepath)      # hotfix 阶段 4 编排
        → FileOpenService 校验来源（用户/拖放/插件/会话恢复/设置导入）
        → 判断是否笔记库外文件 → workspace_store.add_external_file()
        → EditorTabWidget.open_file(filepath)
           → 编码级联检测
           → 判断是否 Markdown → 创建 Editor 或 MarkdownPreviewWidget
           → 经 DocumentRegistry 注册 document_id（已打开同路径 → attach 共享 Document）
           → set_file_type() → 绑定语法高亮 + auto_minimap
        → 最近文件记录（refresh_recent_files 过滤已不存在路径并持久化）
     → MainWindow 保留 UI 副作用（错误弹窗 / 文件树刷新 / 菜单重建）
```

### 6.2 在线挂机资源发放

```
idle_reward_timer (每60秒，由 TimerManager 管理)
  → MainWindow._on_idle_reward()
     → GameEngine.calculate_idle_reward()
     → config.add_resource("fuel", 5)
     → config.add_resource("ammo", 5)
     → config.add_resource("steel", 5)
     → bauxite_counter++ → 满3时 add_resource("bauxite", 5)
     → resource_bar.refresh()
```

### 6.3 标签拖拽移动文件

```
DraggableTabBar.mouseMoveEvent (鼠标离开标签栏)
  → QDrag(MIME_TAB_FILEPATH = filepath UTF-8)
  → DroppableTreeView.dropEvent
     → 解析 MIME → 确定目标文件夹
     → FileTreeWidget.file_move_requested(src, dest)
     → MainWindow._on_file_move_from_tree(src, dest)
        → EditorTabWidget.move_file_to_folder(src, dest)
           → 保存最新内容 → shutil.move → DocumentRegistry.move_path re-key + bind_path 广播
        → secretary.show_message("已移动...")
```

---

## 7. 已实现机制：打字奖励

打字奖励系统已接入：

- **设计**：在编辑器的 `textChanged` 中接入有效击键统计，通过 `chars_typed` 信号传递字符增量到 `MainWindow._on_chars_typed()`，应用递减收益算法后调用 `GameEngine.add_typing_reward()` 转化为资源。
- **规则**：
  - 每日前 1000 字 100% 计入；1000–3000 字 40%；更高 10%（递减收益）
  - 每日上限 10,000 字符
  - 奖励按 1:1:1:0.2 比例分配到燃料/弹药/钢材/铝材
- **实现**：
  - `editor_tabs.py` 新增 `chars_typed` 信号，在 `_on_text_changed()` 中计算字符增量并发射
  - `MainWindow._on_chars_typed()` 实现递减收益算法
  - `GameEngine.add_typing_reward()` 将奖励转化为四项资源
  - 粘贴检测：`Editor` 重写 `insertFromMimeData()` 设置 `_is_pasting` 标志，`_on_text_changed()` 检查此标志跳过粘贴的打字奖励计数；粘贴检测阈值 `_PASTE_THRESHOLD = 50`，避免 IME 整句输入误判

未完成的建造/图鉴/车库/游戏设置规划见 [roadmap.md](roadmap.md)。

---

## 8. 快捷键总览

| 分类   | 快捷键                                   | 功能                             |
| ------ | ---------------------------------------- | -------------------------------- |
| 文件   | `Ctrl+N/O/S/Shift+S/W`                   | 新建/打开/保存/另存为/关闭标签   |
| 编辑   | `Ctrl+Z/Y/X/C/V/A`                       | 撤销/重做/剪切/复制/粘贴/全选    |
| 查找   | `Ctrl+F/H/G`, `F3/Shift+F3`              | 查找/替换/转到行/下一个/上一个   |
| 行操作 | `Ctrl+Shift+K`, `Alt+↑↓`, `Ctrl+Shift+D` | 删除行/移动行/复制行             |
| 大小写 | `Ctrl+Shift+U`                           | 切换大小写                       |
| 视图   | `Ctrl+B/M/Shift+P`, `F11`, `Ctrl+±0`     | 文件树/缩略图/命令面板/全屏/缩放 |
| 导航   | `Ctrl+1/2/3/4`                           | 记事本/建造/车库/图鉴            |

---

## 9. 依赖与运行

### 运行依赖

```bash
pip install PyQt6>=6.11.0 shiboken6>=6.11.2 Pygments>=2.21.0 markdown>=3.10.3 Pillow>=12.3.0 send2trash>=2.1.0 markdown-it-py>=4.2.0 mdit-py-plugins>=0.6.1 qasync>=0.28.0 webview2-Microsoft.Web.WebView2.Core>=3.2.1 winrt-Windows.Foundation>=3.2.1
python main.py
```

> 预览与 PDF 导出依赖系统安装的 **Microsoft Edge WebView2 Runtime**（Windows 11 与多数 Windows 10 已预装，**不随包分发**）；缺失时启动会记录 error 日志并在窗口显示后弹一次安装指引，预览区同时显示可读提示。
> `qasync` / `webview2-*` / `winrt-*` 均为 Windows 专用；完整依赖清单以 `pyproject.toml` / `requirements.txt` 为准。

### 开发依赖

```bash
pip install pytest>=9.0 pytest-cov pytest-qt  # 单元测试
pip install mypy>=1.20                         # 类型检查
```

### 单元测试

项目共 33 个测试文件（`tests/test_*.py`），覆盖核心模块、编辑器、游戏系统、安全模块及可扩展性架构。另有 `tests/benchmarks/` 存放性能基准测试。运行方式：`pytest tests/ -v`。测试文件命名约定为 `test_<module>.py`，每个测试文件覆盖对应模块的关键路径。

---

## 10. 架构约束与开发规范

以下为本项目必须遵守的架构约束（版本特定的修复细节见 [../CHANGELOG.md](../CHANGELOG.md)）：

### 通用约束

1. **编码保持**：打开文件时检测编码并记录在 `SharedDocument.encoding`，保存时使用相同编码
2. **资源文件路径**：立绘/图标始终从 `_app_dir`（程序目录）读取，不随 `_base_path` 变化
3. **auto_minimap**：开启时 .txt/.md 不显示缩略图，关闭时使用全局 `show_minimap` 设置
4. **打字统计日期重置**：`get_today_chars_typed()` 自动比较 `today_date` 并在跨日时归零
5. **Feature Flag**：所有性能优化特性通过 `utils/feature_flags.py` 控制，配置持久化到 `feature_flags.json`
6. **Mixin 模式**：`Editor` 类通过 Mixin 继承组合功能，mypy 对 Mixin 文件禁用 `attr-defined`/`arg-type` 检查
7. **异步渲染线程安全**：`AsyncHighlightRenderer` 使用 `QueuedConnection` 信号通信，禁止在非主线程操作 UI 元素
8. **虚拟滚动**：大文件（≥50000行）自动启用延迟语法高亮
9. **高 DPI 缩放**：`main.py` 已启用 `AA_EnableHighDpiScaling`，`dpi_helper.scale()` 系列函数在生产环境中为 no-op
10. **行尾符**：所有源文件使用 LF 行尾符，配合 `.gitattributes` 的 `* text eol=lf` 规则

### 安全约束

11. **路径安全**：所有文件操作路径必须通过 `PathValidator` 白名单验证，禁止直接使用用户输入构造文件路径。`config.py` 在初始化时将 `_app_dir` 和 `_base_path` 加入白名单
12. **文件操作安全**：使用 `FileGuard.safe_read()` / `safe_write()` 替代直接 `open()`，确保文件大小和超时控制。`safe_write`/`safe_write_bytes` 原子写入（同目录临时文件 + `os.replace`），崩溃/断电不留下半写文件
13. **输入验证**：所有用户输入（文件名、搜索内容、设置值）必须通过 `InputValidator` 验证。文件名用 `validate_filename_strict()`，搜索内容用 `validate_search()`，设置值用 `validate_setting()`
14. **存档保存失败提示**：`SavegameManager.save()` 返回 `SavegameSaveResult` 枚举，写入失败时返回 `WRITE_FAILED`。MainWindow 在关闭时检查此状态并弹出警告
15. **导出安全**：Markdown 转 PDF/HTML 时显式禁用 raw HTML（`MarkdownIt("commonmark", {"html": False})`），python-markdown fallback 仅启用 `tables` 扩展
16. **日志脱敏**：`ErrorHandler.sanitize()` 自动脱敏 password/token/secret/api_key/key 等敏感字段，日志中不出现明文凭据

### 保存与会话约束

18. **保存状态机**：明确 dirty→saving→clean/save_failed 状态流转，保存失败恢复 dirty，`SaveTaskManager` 统一生命周期管理
19. **关闭等待保存**：`closeEvent` 两阶段关闭，保存中/保存失败不退出，全部成功后才最终关闭
20. **临时会话恢复**：`TempSessionManager` 管理 autosave session，异常退出恢复提示在 `window.show()` 之后弹出
21. **FileOpenService 安全入口**：统一校验文件打开来源（用户/拖放/插件/会话恢复/设置导入），分类控制路径白名单/扩展名/二进制检测，`_is_inside_root` 使用 `os.path.commonpath` 防前缀绕过

### 主题约束

22. **主题全局生效**：所有需要响应主题切换的 UI 组件应继承 `ThemeAwareMixin`，实现 `_apply_theme_colors()` 方法。`ThemeAwareMixin` 自动订阅 `ThemeManager.theme_committed` 信号
23. **硬编码颜色迁移**：编辑器、Markdown 预览、弹窗中残留的硬编码颜色应逐步迁移到主题 token 系统，迁移方向参考 [color_audit.md](theme-design/color_audit.md)（VS Code Dark Modern / Dark+）

### 插件约束

24. **可信插件模型**：插件代码运行在主程序进程中（GUI 线程），能力系统只限制 PanzerNote 暴露的 API 边界，不是完整安全沙箱。请只安装可信来源的插件
25. **能力声明两层结构**：manifest 声明 `capabilities` → `CAPABILITY_PERMISSIONS` 映射内部权限；调用未声明/不存在的能力抛 `PluginCapabilityError`。命名空间类能力（`data.read`/`data.write`）用 `pass_plugin_id` 将调用者插件 id 传入 impl，天然隔离命名空间
26. **文件安全入口**：`ctx.workspace.open_file()` 走 `FileOpenService.PLUGIN` 路径校验；`ctx.data` 数据目录由宿主从插件 id 派生（`data/plugin_data/{id}/data.json`），插件不可指定路径，写盘走 `FileGuard.safe_write`（原子写 + 1MB 上限）
27. **主线程 + 异常隔离 + 启动恢复**：所有生命周期钩子与回调在 GUI 线程执行，无插件线程与超时；生命周期异常 → `ERROR`（可重载），回调（命令/菜单/事件）异常 → 仅 log 不自动禁插件；事件订阅走白名单 + 100ms 节流 + 单插件单事件上限 5，卸载自动解绑。插件启动走**延迟加载**（窗口显示后 `QTimer.singleShot(0, ...)` 激活 `enabled` 插件，不进启动关键路径）；**启动恢复 marker** 覆盖 on_load→on_activate 全程（残留 marker → 安全模式跳过，需手动处理）

### 性能约束

28. **自动配对性能**：`AutoPairHandlerMixin` 使用 `frozenset` 缓存实现 O(1) 入口过滤，`_doc_char_at()` 替代 `toPlainText()` 全文复制，`_wrap_selection()` 替代 `selectedText()` 大字符串复制。修改 `AUTO_PAIR_CHARS` 字典后缓存自动失效重建
29. **粘贴检测**：`Editor` 重写 `insertFromMimeData()` 设置 `_is_pasting` 标志，`EditorTabWidget._on_text_changed()` 检查此标志跳过粘贴的打字奖励计数。`_PASTE_THRESHOLD = 50`，仅字符增量 ≤50 且非粘贴时计入奖励
30. **MarkdownIt 实例复用**：`MarkdownPreviewWidget._create_md_parser()` 在 `__init__` 中创建一次解析器实例并缓存为 `_md_parser`，`_render_markdown()` 直接调用缓存实例渲染
31. **文件保存异步化**：`SaveTask`（`QRunnable`）+ `SaveTaskSignals`（`QObject`）将 `safe_write` 磁盘 IO 放到 `QThreadPool.globalInstance()` 后台线程执行；`safe_write` 原子化（同目录临时文件 + `os.replace`），并发写目标始终是完整版本（last-write-wins），共享 Document 另有跨面板唯一门闩保证最新内容最后落盘。保存失败时回滚修改状态并恢复标签页 `*` 标记
32. **Markdown 预览 JS 局部更新**：首次渲染经适配器 `set_html` 整页加载模板，`load_finished` 后标记 `_html_template_loaded = True`，后续经 `run_javascript` 仅更新 `innerHTML`。切换文档时自动重置标志。注意：这不是真正 block 级增量渲染
33. **Minimap 块级增量失效**：`MinimapWidget` 改用 `QTextDocument.contentsChange` 信号，精确计算受影响缓存块范围并标记为脏块（`_block_dirty`），仅重新渲染脏块。常规打字仅重绘 1 个块，节省约 95% 渲染开销
34. **状态栏信号驱动统计**：`signal_driven_stats` 默认开启，`characterCount()` 避免全文复制，词数 800ms 防抖，行列号由 `cursorPositionChanged` 驱动
35. **搜索高亮集中管理**：`SearchService` 封装查找/替换，`QTextDocument.find()` 权威光标位置，`ExtraSelectionManager` 统一高亮层，`replace_all` 从后向前逐匹配替换
36. **运行时性能探针（Wave 4 E1）**：大文件加载/首屏/滚动热路径经 `utils/perf_probe.py` 的 `measure(name, fn, threshold_ms)` 埋点，debug 级日志过滤高频滚动噪音；新增热路径计时默认经探针，不裸写 `time.time()`
37. **lazy 高亮多 View 协作（Wave 4 E2）**：`DocumentLazyHighlightCoordinator` 以 Document 为粒度聚合各 View 可视区（并集），禁止回到 per-View 独立高亮（会破坏 Document 级共享 highlighter 的一致性）；滚动上报按 View、调度归 coordinator
38. **Large File Mode（Wave 4 E3/E4）**：达阈值（≥1 万行）自动降级补全/折叠/Minimap/预览等高成本功能，`large_file_mode` / `lazy_highlight` flag 默认 False（运行时按需激活），禁用全局残留；降级功能须可配置可回退
39. **Markdown HTML render cache（Wave 4 C）**：`document_render_cache.py` 以 Document revision 为键缓存最终 HTML，Document 改动只渲染一次、多 View 共用；新增 Markdown 渲染路径应优先走缓存

### 工程约束

40. **快捷键管理**：`ShortcutManager` 已接入 `MenuBuilder`，所有菜单项通过 `manager.register()` 注册，自定义快捷键功能已生效。新增菜单项必须通过 ShortcutManager 注册
41. **错误提示**：使用 `ErrorHandler.show_error()` / `ErrorHandler.show_from_exception()` 替代直接 `QMessageBox`，确保敏感信息过滤和统一分类提示
42. **设置导入校验**：`ConfigImportService` 逐字段校验类型/值范围，非法字段跳过并报告，不直接 `_settings.update()`
43. **集中式版本管理**：`src/__init__.py` 中的 `__version__` 为唯一真相源，所有模块通过 `from src import __version__` 引用。`pyproject.toml` 使用动态版本配置，`scripts/verify_version.py` 提供一致性验证，`main.py` 启动时自动检查
44. **依赖梳理**：`pyproject.toml` 分组 format/dev/all，所有运行时依赖均为必需
45. **增量渲染器命名澄清**：`incremental_renderer.py` 确认为全文 hash 渲染缓存，文档不宣称"真正增量渲染"
46. **分屏与共享文档语义**：`ViewCoordinator.split_editor()` 打开新空白文件（菜单文本标注"独立编辑"）；同一文件在多个面板打开时共享同一 `SharedDocument`（3.5.8，跨面板联动编辑）——内容/编码/eol/dirty/折叠/书签单一源，每个 View 只持有自己的 `ViewState` 与 `DocumentViewBinding`。共享 Document 的保存以 Document 级状态机为跨面板唯一门闩（全局同时最多一个写盘任务）。禁止创建两个不同 Document 指向同一路径（`DocumentRegistry` 路径占用拒绝）
47. **封装规范**：禁止通过 `self.config._savegame_manager` 等私有属性访问，使用 `self.config.savegame_manager` 公开属性；新代码优先经 `app_context.<子模块>` 直连（hotfix 阶段 7），Config 门面仅作过渡兼容
48. **数据防泄漏**：对外暴露配置/存档数据一律走只读视图或拷贝——`savegame_manager.get_savegame()` 返回 MappingProxyType、`get_resources()` 返回拷贝、`settings_store.as_dict()`/`workspace_store.as_dict()` 返回深拷贝。禁止直接返回内部可变 dict 引用
49. **状态单一源**：标签状态一律走 `SharedDocument`（内容/编码/eol/dirty/折叠/书签）与 `ViewState`（cursor/scroll），禁止回退到影子状态模型（Wave 4 D 已删除 TabState/document_model.py）；workspace 序列化唯一出口为 `workspace_entries.py` 适配层
50. **白名单单一来源**：workspace 字段白名单由 `WorkspaceStore._KNOWN_WORKSPACE_KEYS`（由 `DEFAULT_WORKSPACE` 派生）提供，`ConfigImportService` 直接复用，禁止另行复制定义

---

_本文档基于 PanzerNote v2.3.0 源码整理。版本变更见 [../CHANGELOG.md](../CHANGELOG.md)，未完成规划见 [roadmap.md](roadmap.md)。_
