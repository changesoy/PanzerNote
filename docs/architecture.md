# PanzerNote 架构与设计文档

> 本文档面向开发者和 AI，描述项目的目标、代码结构、核心模块、数据流与架构约束。
> 用户使用指南、版本变更、未完成规划请参考 [../README.md](../README.md)、[../CHANGELOG.md](../CHANGELOG.md)、[roadmap.md](roadmap.md)。

---

## 1. 项目背景

PanzerNote 是一款以已停服二次元游戏《战车少女》（PanzerMaiden）为主题的 **PC 端离线单机记事本程序**，用于私人纪念。核心理念：

- **记事本为主体**：功能完整的多标签文本编辑器，支持 Markdown 分屏预览与 30+ 语言语法高亮
- **游戏系统为灵魂**：通过日常书写行为积累资源 → 资源投入建造 → 抽取战车娘角色 → 点亮图鉴
- **小巧、离线、本地存档**：所有数据存储在本地 JSON 文件中，不依赖网络

**技术栈**：Python 3.11+ / PyQt6 / Pygments / markdown 库 / markdown-it-py / QWebEngine

---

## 2. 模块状态总览

| 模块                 | 状态      | 说明                                                                                          |
| -------------------- | --------- | --------------------------------------------------------------------------------------------- |
| 多标签文本编辑器     | ✅ 完成   | 行号、语法高亮、自动缩进、括号配对、括号匹配高亮、行操作、大小写转换、转到行、JSON/XML 格式化 |
| 缩进/行尾配置        | ✅ 完成   | indent_size/use_tabs 配置；LF/CRLF 探测与规范化；状态栏切换行尾格式                           |
| 文本统计             | ✅ 完成   | CJK 按字计数 + 拉丁按词计数；状态栏信号驱动统计                                               |
| Markdown 分屏预览    | ✅ 完成   | 实时渲染 + 代码块高亮 + 一键复制 + 本地图片 + 源码行号同步 + 折叠同步                         |
| 代码缩略图 (Minimap) | ✅ 完成   | 鸟瞰图、点击/拖拽导航、块级缓存增量失效、跳过折叠隐藏块                                       |
| Markdown 标题折叠    | ✅ 完成   | 标题层级折叠 + 代码缩进折叠 + 工作区持久化 + 跳转自动展开                                     |
| Markdown 大纲导航    | ✅ 完成   | 解析标题树、点击跳转、按文件类型显隐                                                          |
| 命令面板             | ✅ 完成   | Ctrl+Shift+P / F1 唤起、搜索执行命令、位置记忆                                                |
| 跨文件搜索           | ✅ 完成   | 后台线程遍历 + 正则/纯文本匹配 + 按文件分组 + 双击跳转                                        |
| 文档缓冲区自动补全   | ✅ 完成   | 词频匹配 + Enter/Tab 接受 + IME 组字期间不弹出                                                |
| 增强型查找替换       | ✅ 完成   | 正则、大小写敏感、全词匹配、匹配计数、ExtraSelections 高亮                                    |
| 侧栏面板宿主         | ✅ 完成   | 多面板注册/切换/宽度记忆                                                                      |
| 文件树               | ✅ 完成   | 文件树 + 外部文件区 + 右键菜单 + 接受标签拖拽移动文件                                         |
| 标签页拖拽           | ✅ 完成   | 标签内排序 + 拖拽到文件树移动文件                                                             |
| 资源栏               | ✅ 完成   | 四资源显示 + 打字统计                                                                         |
| 在线/离线挂机        | ✅ 完成   | 在线每分钟 +5/+5/+5、铝材每3分钟+5；离线 1/3 向大取整，上限 24h                               |
| 打字奖励             | ✅ 完成   | textChanged 接入 → 递减收益算法 → 资源奖励（1:1:1:0.2）                                       |
| 每日签到             | ✅ 完成   | 每日首次启动发放奖励（各+100）                                                                |
| 小秘书               | ✅ 完成   | 立绘 + 台词气泡 + 事件台词 + 自定义角色/皮肤/状态                                             |
| 书签持久化           | ✅ 完成   | 书签保存到 workspace.json，关闭重开后恢复                                                     |
| 设置系统             | ✅ 完成   | settings.json + workspace.json + savegame.json，首次运行对话框                                |
| 安全防护体系         | ✅ 完成   | 路径验证/文件操作安全/输入验证/拖放白名单                                                     |
| 插件系统             | ✅ 完成   | 生命周期/线程包装/12 种权限/热加载，2 个示例插件 + API 文档                                   |
| 主题系统             | ✅ 完成   | JSON/YAML 外部主题/解析引擎/QSS 生成/预览/ThemeAwareMixin 全局生效/原生标题栏深色             |
| 集中式版本管理       | ✅ 完成   | `src/__init__.py` 唯一真相源 + `verify_version.py` 一致性验证                                 |
| 建造系统             | 🔲 规划中 | 详见 [roadmap.md](roadmap.md)                                                                 |
| 图鉴系统             | 🔲 规划中 | 详见 [roadmap.md](roadmap.md)                                                                 |
| 车库系统             | 🔲 规划中 | 详见 [roadmap.md](roadmap.md)                                                                 |
| 游戏设置界面         | 🔲 规划中 | 详见 [roadmap.md](roadmap.md)                                                                 |

---

## 3. 目录结构

```
PanzerNote/
├── main.py                         # 程序入口（高DPI、字体、图标、首次运行引导、启动分析、版本一致性检查）
├── requirements.txt                # 运行依赖
├── pyproject.toml                  # 项目配置（pytest/mypy/依赖/动态版本引用）
├── .gitignore                      # Git 忽略规则
├── .gitattributes                  # Git 属性（* text=auto eol=lf 行尾符统一）
├── user_data_path.txt              # 持久化用户数据路径
├── CHANGELOG.md                    # 版本变更记录
├── LICENSE                         # GPL-3.0 许可证
│
├── tests/                          # 单元测试 + 性能基准测试（tests/benchmarks/）
│
├── src/                            # ══════ 源代码 ══════
│   ├── __init__.py                 # 版本号唯一真相源（__version__/get_version/get_version_tuple）
│   ├── main_window.py              # 主窗口（菜单栏 + 布局组装 + 事件路由 + 插件/主题集成）
│   │
│   ├── core/                       # ── 核心模块 ──
│   │   ├── config.py               # 配置管理中枢（settings/workspace 读写 + SavegameManager/SecurityManager 组合委托）
│   │   ├── config_import_service.py # 配置导入服务（类型校验 + 白名单）
│   │   ├── savegame_manager.py     # 存档管理器（加载/保存/每日签到）
│   │   ├── security_manager.py     # 安全管理器（PathValidator/FileGuard/InputValidator 集成管理）
│   │   ├── timer_manager.py        # 定时器管理中心
│   │   ├── event_bus.py            # 事件路由系统
│   │   ├── menu_builder.py         # 菜单构建器（已接入 ShortcutManager）
│   │   └── shortcut_manager.py     # 快捷键管理器
│   │
│   ├── editor/                     # ── 编辑器模块 ──
│   │   ├── editor.py               # 核心编辑器（行号、缩略图、语法高亮、自动缩进、虚拟滚动）
│   │   ├── editor_tabs.py          # 多标签管理（打开/保存/关闭/编码检测/拖拽/文件移动）
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
│   │   ├── temp_session_manager.py # 临时会话恢复（异常退出 autosave session 恢复）
│   │   ├── virtual_scroll.py       # 虚拟滚动管理器（大文件延迟语法高亮）
│   │   ├── async_highlight.py      # 异步代码高亮渲染器（QThread + 任务队列）
│   │   ├── incremental_renderer.py # 渲染缓存（MD5 哈希缓存，全文级）
│   │   ├── syntax_highlighter.py   # 语法高亮（Pygments 适配器 + Markdown 专用高亮器）
│   │   ├── highlight_themes.py     # 代码高亮主题
│   │   ├── webengine_runtime.py     # WebEngine 启动锚点管理（预初始化 + 锚点释放）
│   │   ├── markdown_preview.py     # Markdown 分屏预览（源码行号同步 + 代码块高亮 + 本地图片）
│   │   ├── minimap.py              # 代码缩略图（块级缓存增量失效）
│   │   ├── find_replace.py         # 查找替换栏
│   │   ├── search_service.py       # 搜索服务（QTextDocument.find 权威光标 + 从后向前替换）
│   │   ├── extra_selection_manager.py # 高亮层管理（统一 ExtraSelection 避免互相覆盖）
│   │   ├── secure_markdown_renderer.py # 安全 Markdown 渲染（清洗 script/iframe/onerror/javascript:）
│   │   ├── export_service.py       # 导出服务（HTML/PDF 统一安全管线）
│   │   ├── file_open_service.py    # 文件打开安全入口（来源校验/路径白名单/二进制检测）
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
│   │   ├── first_run_dialog.py     # 首次运行对话框
│   │   ├── command_palette.py      # 命令面板（Ctrl+Shift+P / F1 唤起，搜索并执行命令）
│   │   ├── side_panel_host.py      # 侧栏面板宿主（管理多面板注册/切换/持久化）
│   │   └── shortcut_panel.py       # 快捷键提示面板
│   │
│   ├── security/                   # ── 安全模块 ──
│   │   ├── __init__.py             # 安全模块导出与异常定义
│   │   ├── path_validator.py       # 路径安全验证
│   │   ├── file_guard.py           # 文件操作安全控制
│   │   ├── file_access_context.py  # 文件访问上下文枚举
│   │   └── input_validator.py      # 输入验证框架
│   │
│   ├── plugins/                    # ── 插件系统 ──
│   │   ├── plugin_base.py          # 插件基类与元数据定义
│   │   ├── plugin_api_views.py     # 插件 API 只读视图（ReadOnlyConfigView）
│   │   ├── plugin_sandbox.py       # 插件包装器（线程隔离/超时/权限控制/PluginAPI）
│   │   ├── plugin_manager.py       # 插件管理器
│   │   └── plugin_manager_dialog.py # 插件管理对话框
│   │
│   ├── themes/                     # ── 主题系统 ──
│   │   ├── theme_engine.py         # 主题引擎（JSON/YAML 加载/QSS 生成）
│   │   ├── theme_aware_mixin.py    # 主题感知混入
│   │   └── theme_preview.py        # 主题预览对话框
│   │
│   └── utils/                      # ── 工具模块 ──
│       ├── logger.py               # 结构化日志系统
│       ├── exceptions.py           # 统一异常处理 @safe_call
│       ├── error_handler.py        # 统一错误提示系统
│       ├── dpi_helper.py           # 高 DPI 缩放适配
│       ├── feature_flags.py        # Feature Flag 系统
│       ├── window_theme.py         # Windows 原生标题栏深色辅助（DWM 非客户区）
│       └── lazy_loader.py          # 启动性能分析（StartupProfiler）
│
├── scripts/
│   └── verify_version.py           # 版本一致性验证工具
│
├── docs/                           # 文档
│   ├── architecture.md             # 本文件
│   ├── roadmap.md                  # 未完成规划
│   └── color_audit.md              # 硬编码颜色审计
│
├── data/                           # 数据 & 资源（程序目录）
│   ├── assets/
│   │   ├── icons/
│   │   └── portraits/              # 角色立绘
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

### 4.1 配置管理 (`core/config.py`)

Config 类是整个应用的配置中枢，通过组合方式委托 `SavegameManager` 和 `SecurityManager` 管理存档和安全功能，自身负责 settings/workspace 两个 JSON 文件：

| 文件             | 位置                         | 职责                                                           | 管理者            |
| ---------------- | ---------------------------- | -------------------------------------------------------------- | ----------------- |
| `settings.json`  | `{base_path}/data/config/`   | 所有用户偏好设置（编辑器、游戏、小秘书、视图、窗口、快捷键）   | `Config`          |
| `workspace.json` | `{base_path}/data/config/`   | 会话状态（打开的文件列表、最近文件、外部文件、文件树展开状态） | `Config`          |
| `savegame.json`  | `{base_path}/data/gamedata/` | 游戏存档（四资源、核心数、打字统计、建造队列、拥有角色、成就） | `SavegameManager` |

**路径机制（方案A）**：

- 程序目录下保存 `user_data_path.txt`，记住用户选择的数据存储路径
- 首次运行由 `FirstRunDialog` 引导选择
- 资源文件（立绘、图标等）始终从**程序目录** `_app_dir` 读取
- 用户数据（笔记、配置、存档）从 `_base_path` 读取

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

| 模块                          | 职责                                                                             |
| ----------------------------- | -------------------------------------------------------------------------------- |
| `main_window.py`              | 布局组装、菜单动作代理、状态管理、插件/主题集成、统一窗口显示入口（`present()`） |
| `editor/webengine_runtime.py` | WebEngine 启动锚点管理：首个预览挂载前预初始化 Qt WebEngine，挂载后释放锚点      |
| `core/timer_manager.py`       | 定时器生命周期管理（自动保存/统计/挂机奖励）                                     |
| `core/event_bus.py`           | 信号连接集中管理，解耦模块间通信                                                 |
| `core/menu_builder.py`        | 菜单栏构建逻辑，已接入 ShortcutManager                                           |
| `game/game_engine.py`         | 挂机收益计算（在线/离线奖励、打字奖励、资源上限检查）                            |

**定时器**（由 `TimerManager` 管理）：

- `auto_save_timer`（默认30秒）→ 调用 `save_all_to_temp()`
- `stats_timer`（500ms）→ 更新状态栏和资源栏统计
- `idle_reward_timer`（60秒）→ 在线挂机资源发放

**挂机机制**（由 `GameEngine` 计算）：

- **在线**：每分钟 fuel/ammo/steel +5，bauxite 每3分钟+5（用 `bauxite_counter` 计数）
- **离线**：启动时 `GameEngine.calculate_offline_rewards()` 根据 `last_login` 计算时间差，收益 = 在线的 1/3（向大取整），上限24h，最少5分钟

**窗口启动与会话恢复**：

- `present()` — 统一的窗口显示入口（替代直接 `show()`）。`__init__()` 期间窗口始终不可见，最大化场景使用 `showMaximized()` 让 Qt 以最终尺寸完成首次渲染，避免普通尺寸→最大化尺寸的两段式跳变
- `_restore_window_geometry()` — 在窗口不可见状态下恢复几何和最大化状态。最大化场景预缩放控件树到屏幕可用尺寸，消除首帧 paint 时的视觉撕裂
- `_build_restore_plan(open_files)` — 会话恢复计划：返回 `(pre_show_entries, deferred_entries)`。`pre_show_entries` 包含首个标签和首个 Markdown 标签（若二者是同一文件，只恢复一次），在窗口显示前同步挂载；`deferred_entries` 在窗口显示后通过 `QTimer.singleShot(0, ...)` 异步恢复
- `_restore_cursor_for_tab(file_info, tab_index)` — 提取的光标/滚动位置恢复辅助函数，支持 `Editor` 和 `MarkdownPreviewWidget`
- `WebEngineRuntime` — 在 `__init__` 中创建，布局 setup 期间调用 `prepare_startup_anchor()` 在编辑器容器中挂载一个 1×1 的最小 QWebEngineView，强制 Qt WebEngine 提前初始化，避免首个 Markdown 预览打开时的白屏延迟。首个真实预览挂载后调用 `notify_real_view_attached()` 释放锚点

### 4.3 编辑器 (`editor/editor.py`)

基于 `QPlainTextEdit`，使用 Mixin 模式组合功能。类继承：`Editor(AutoPairHandlerMixin, EditorActionsMixin, QPlainTextEdit)`

| 模块                              | 职责                                                               |
| --------------------------------- | ------------------------------------------------------------------ |
| `editor/editor.py`                | 核心编辑器（行号、缩略图、语法高亮、自动缩进、虚拟滚动、粘贴检测） |
| `editor/editor_actions.py`        | 行操作、大小写转换、JSON/XML 格式化（Mixin）                       |
| `editor/auto_pair_handler.py`     | 括号/引号自动配对（Mixin，frozenset O(1) 过滤）                    |
| `editor/bracket_matcher.py`       | 括号匹配高亮（纯函数，扫描配对位置，支持中英文括号）               |
| `editor/indentation.py`           | 缩进统一入口（缩进宽度/缩进文本，禁止硬编码）                      |
| `editor/eol_utils.py`             | 行尾探测与规范化纯函数（LF/CRLF/CR）                               |
| `editor/text_stats.py`            | 文本统计纯函数（CJK 按字计数 + 拉丁按词计数）                      |
| `editor/folding.py`               | 折叠管理器（Markdown 标题折叠 + 代码缩进折叠）                     |
| `editor/outline_parser.py`        | Markdown 标题解析器（纯函数，提取标题层级与行号）                  |
| `editor/outline_panel.py`         | Markdown 大纲导航面板（QTreeWidget 展示标题树）                    |
| `editor/completion.py`            | 文档缓冲区自动补全（词频匹配 + IME 组字期间不弹出）                |
| `editor/find_in_files_service.py` | 跨文件搜索后台服务（QThread 遍历 + 正则/纯文本匹配）               |
| `editor/find_in_files_panel.py`   | 跨文件搜索结果面板（按文件分组 + 双击跳转）                        |
| `editor/save_task.py`             | 后台文件保存任务（SaveTask + QThreadPool 异步写入）                |
| `editor/virtual_scroll.py`        | 延迟高亮管理器（大文件延迟语法高亮）                               |

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

### 4.4 标签页管理 (`editor/editor_tabs.py`)

| 组件              | 说明                                                                                  |
| ----------------- | ------------------------------------------------------------------------------------- |
| `DraggableTabBar` | 继承 `QTabBar`，标签内拖拽 = 重排序，拖出标签栏 = 发起 `QDrag`（携带文件路径 MIME）   |
| `EditorTabWidget` | 继承 `QTabWidget`，管理 `_tab_info` 字典（filepath/modified/encoding/is_markdown 等） |
| `SaveAsDialog`    | 自定义另存为对话框，支持编码选择（UTF-8/GBK/UTF-16）                                  |

**核心逻辑**：

- `open_file()` — 编码级联检测（UTF-8 → GBK → UTF-16 → 容错UTF-8），Markdown 文件自动使用 `MarkdownPreviewWidget`；新增 `render_preview` 参数（默认 `True`），设为 `False` 时延迟预览渲染以加速启动恢复
- `_on_text_changed()` — 比较当前内容与 `last_saved_content`，决定是否标记为已修改（标签名加 ` *`）；粘贴操作不计入打字奖励
- `move_file_to_folder()` — 先保存最新内容 → `shutil.move` → 更新 `_tab_info` 中的 filepath
- 所有编辑操作（undo/redo/cut/copy/paste/行操作/大小写/格式化）通过代理方法转发给当前编辑器

### 4.5 Markdown 预览 (`editor/markdown_preview.py`)

**渲染管线**：

```
编辑器文本 → markdown 库渲染 HTML → _process_code_blocks()（Pygments 内联样式高亮 + 浅蓝容器 + Unicode 标记）
           → _resolve_local_images()（相对路径 → file:// 绝对路径）
           → PREVIEW_HTML_TEMPLATE 包裹 → QTextBrowser/QWebEngineView 显示
```

**异步渲染管线**（Feature Flag `async_highlight` 控制）：

```
编辑器文本 → markdown 库渲染 HTML → _process_code_blocks_async()（代码块先用纯文本占位）
           → AsyncHighlightRenderer 后台线程渲染代码高亮
           → _on_async_highlight_done() 信号回调替换占位符为高亮结果
```

**增量渲染**（Feature Flag `markdown_incremental` 控制）：

- `IncrementalRenderer` 基于文本 MD5 哈希缓存渲染结果，相同文本直接返回缓存（全文级缓存，非行级增量）

**浮动复制按钮** (`PreviewBrowser`)：

- 在每个代码块 HTML 首尾嵌入不可见 Unicode 标记（⌜N⌝ / ⌞N⌟）
- `setHtml` 后用 `QTextDocument.find()` 缓存标记的 QTextCursor
- `mouseMoveEvent` 判断鼠标是否在某代码块垂直范围内，是则显示浮动复制按钮
- 防抖 30ms + 按钮 enter/leave 处理防止闪烁

**源码行号同步**：

- `_render_markdown_with_source_map()`：使用 `markdown-it-py` 的 `token.map` 给块级节点注入 `data-source-line` 属性（1-based 行号），覆盖 heading_open/paragraph_open/blockquote_open/bullet_list_open/ordered_list_open/list_item_open/table_open/thead_open/tbody_open/tr_open/hr/fence/code_block 共 13 种 token
- `_build_container()` 支持 `source_line` 参数：代码块外层容器携带 `data-source-line` 属性
- `_current_editor_top_line()`：通过 `cursorForPosition(QPoint(0, 0))` 获取编辑器视口顶部行号
- `_sync_scroll()` 改为源码行号同步：QWebEngineView 通过 `runJavaScript` 调用 `scrollToSourceLine(line)`，QTextBrowser 保留旧百分比同步
- HTML 模板注入 `scrollToSourceLine()` JS 函数：查找 `data-source-line` 节点，在相邻锚点间线性插值计算滚动位置
- HTML 模板注入 `resyncAfterImagesLoaded()` JS 函数：图片 load/error 事件触发后重新同步预览位置

**预览增量更新**：

- `PREVIEW_HTML_TEMPLATE` 包含 `<div id="content">` 包裹内容区
- 首次渲染走 `setHtml` 加载完整模板，`loadFinished` 信号触发后标记 `_html_template_loaded = True`
- 后续渲染通过 `QWebEngineView.page().runJavaScript()` 仅更新 `document.getElementById('content').innerHTML`
- 切换文档（`base_path` 变化）时自动重置标志，强制下次全量加载
- 非 WebEngine 模式（QTextBrowser）仍走全量 `setHtml` 路径

**首次渲染稳定化**：

- 新增 `refresh_preview_now()`，Markdown 文件 `set_base_path()` 后显式触发 `_update_preview()`，不再依赖 `textChanged` 防抖定时器

**非活动预览延迟渲染**：

- 新增 `_preview_dirty` / `_initial_preview_rendered` 标志，`open_file(render_preview=False)` 打开的 Markdown 标签延迟预览渲染
- `invalidate_preview()` — 将预览标记为脏，下次激活时重新渲染
- `ensure_preview_rendered()` — 仅在 `_preview_dirty` 时触发渲染，避免重复计算。选项卡切换时被调用，确保切换到该标签时预览已就绪
- 启动恢复时首个标签以外的 Markdown 文件均以 `render_preview=False` 打开，加速启动

**WebEngine 启动锚点集成**：

- `MarkdownPreviewWidget.__init__()` 接收 `webengine_runtime` 参数
- 首个真实 QWebEngineView 预览挂载到控件树后，调用 `_webengine_runtime.notify_real_view_attached()` 释放 1×1 启动锚点，回收占用的 GPU 资源

### 4.6 代码高亮主题 (`editor/highlight_themes.py`)

- `THEMES` 字典：每个主题 = `{Token: {color, bold, italic, underline, background}}`
- 编辑器端：`get_editor_formats()` → `{Token: QTextCharFormat}`
- 预览端：`highlight_code_html()` → Pygments HtmlFormatter + 内联 style
- 新增主题只需在 `THEMES` 中增加条目 + `settings.json` 中 `editor.code_highlight_theme` 切换
- 深色主题下默认使用 VS Code Dark+ 风格代码高亮（详见 [color_audit.md](color_audit.md)）

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
- `scale(value)` / `scale_size(w, h)` / `scale_font(pt)` / `scale_stylesheet(css)` / `dp(value)`

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

| 集成文件                 | 集成方式                                                                                                                                                                       |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `core/config.py`         | 初始化 `SecurityManager`（内含 PathValidator/FileGuard/InputValidator）和 `CryptoManager`；所有 JSON 读写通过 `FileGuard`；存档支持加密/解密；设置值通过 `InputValidator` 验证 |
| `editor/editor_tabs.py`  | 文件打开通过 `FileGuard.safe_read()` 读取；处理 `FileSizeExceededError`/`FileOperationTimeoutError`                                                                            |
| `editor/file_tree.py`    | 新建文件/文件夹通过 `InputValidator.validate_filename_strict()` 验证；文件创建通过 `FileGuard.safe_write()`                                                                    |
| `editor/find_replace.py` | 搜索内容通过 `InputValidator.validate_search()` 验证，拒绝注入模式                                                                                                             |
| `main_window.py`         | 拖放文件通过 `_SUPPORTED_DROP_EXTS` 白名单校验；PDF/HTML 导出均显式禁用 raw HTML                                                                                               |

#### 4.11.8 拖放文件类型白名单

`MainWindow` 类的 `_SUPPORTED_DROP_EXTS` 类属性（`frozenset`），在 `dropEvent` 中对拖入文件进行扩展名白名单校验。包含允许拖入打开的文件扩展名：`.txt`、`.md`、`.py`、`.c`、`.cpp`、`.h`、`.java`、`.js`、`.json`、`.html`、`.css`、`.xml`、`.yaml`、`.yml`、`.toml`、`.ini`、`.log`、`.sql`、`.sh`、`.go`、`.rs`、`''`（无扩展名）。

**安全意义**：防止用户意外将二进制文件拖入编辑器导致程序异常或显示乱码。

**扩展方式**：修改 `MainWindow._SUPPORTED_DROP_EXTS` 类属性即可，无需修改其他代码。

### 4.12 插件系统 (`plugins/`)

插件系统提供标准化的扩展机制，允许第三方开发者为应用添加功能。插件运行在独立线程中（非进程隔离沙箱），通过受限 API 与主程序交互。

> **⚠️ 可信插件模型声明**：当前插件系统是可信插件模型。插件代码运行在主程序进程中，权限系统只限制 PanzerNote 暴露的 API，不是完整安全沙箱。请只安装可信来源的插件。详细开发文档见 [../plugins/plugin_api.md](../plugins/plugin_api.md)。

#### 4.12.1 插件基类 (`plugins/plugin_base.py`)

- `PluginState` — 插件状态枚举（UNLOADED/LOADED/ACTIVATED/DEACTIVATED/ERROR）
- `PluginPermission` — 权限枚举（12种：READ_SETTINGS/READ_SAVEGAME/READ_WORKSPACE/READ_FILE_TREE/ACCESS_EDITOR/ACCESS_UI/ACCESS_NETWORK/ACCESS_FILESYSTEM/OPEN_FILE/SHOW_MESSAGE/REGISTER_COMMAND/GET_CONFIG）
- `PluginMeta` — 插件元数据（name/version/description/author/min_app_version/permissions/tags），`min_app_version` 默认值引用 `src.__version__`
- `PluginBase` — 插件基类，定义四个生命周期方法：`on_load(api)`/`on_activate()`/`on_deactivate()`/`on_unload()`

**状态转换规则**：

```
UNLOADED → on_load() → LOADED → on_activate() → ACTIVATED
ACTIVATED → on_deactivate() → DEACTIVATED → on_activate() → ACTIVATED
ACTIVATED → on_deactivate() → DEACTIVATED → on_unload() → UNLOADED
LOADED → on_unload() → UNLOADED
任意状态 → 异常 → ERROR
```

#### 4.12.2 插件包装器 (`plugins/plugin_sandbox.py`)

- `PluginAPI` — 受限 API 对象，每次调用检查权限声明
- `PluginSandbox` — 插件包装器，独立线程运行，最大超时30秒（非进程隔离沙箱）
- `SandboxViolationError` — 权限违规异常
- `SandboxTimeoutError` — 执行超时异常

**MVP 限制**：`ACCESS_NETWORK` 和 `ACCESS_FILESYSTEM` 权限被禁止，所有插件仅限只读访问。`MVP_READ_ONLY` 为实例属性防止类级别篡改；`register_command()` 使用 `dict.setdefault()` 原子操作消除 TOCTOU 竞态；`get_config()` 返回 `ReadOnlyConfigView` 只读视图。

**PluginAPI 接口**：

| 方法                                  | 所需权限           | 说明               |
| ------------------------------------- | ------------------ | ------------------ |
| `get_setting(key, default)`           | `READ_SETTINGS`    | 读取设置           |
| `get_editor_setting(key, default)`    | `READ_SETTINGS`    | 读取编辑器设置     |
| `get_game_setting(key, default)`      | `READ_SETTINGS`    | 读取游戏设置       |
| `get_secretary_setting(key, default)` | `READ_SETTINGS`    | 读取小秘书设置     |
| `get_resources()`                     | `READ_SAVEGAME`    | 读取游戏资源       |
| `get_savegame_field(key, default)`    | `READ_SAVEGAME`    | 读取存档字段       |
| `get_recent_files()`                  | `READ_WORKSPACE`   | 读取最近文件       |
| `get_notebooks_path()`                | `READ_FILE_TREE`   | 读取笔记库路径     |
| `get_app_version()`                   | 无                 | 获取应用版本       |
| `open_file(filepath)`                 | `OPEN_FILE`        | 打开文件到编辑器   |
| `show_message(message)`               | `SHOW_MESSAGE`     | 通过小秘书显示消息 |
| `register_command(name, callback)`    | `REGISTER_COMMAND` | 注册自定义命令     |
| `get_config(key, default)`            | `GET_CONFIG`       | 获取只读配置视图   |

#### 4.12.3 插件管理器 (`plugins/plugin_manager.py`)

- `scan_plugins()` — 从 `plugins/` 目录递归扫描插件包
- `load_plugin(name)` — 加载插件（验证清单完整性、版本兼容性、创建沙箱API）
- `activate_plugin(name)` — 激活插件
- `deactivate_plugin(name)` — 停用插件
- `unload_plugin(name)` — 卸载插件
- `reload_plugin(name)` — 热加载插件（停用→卸载→清除缓存→重新加载→恢复状态）

**插件清单 (`plugin.json`) 必需字段**：`name`/`version`/`entry`

### 4.13 主题系统 (`themes/`)

#### 4.13.1 主题引擎 (`themes/theme_engine.py`)

- 支持 JSON/YAML 两种格式的外部主题文件
- 解析颜色方案（主色/背景/前景/强调色/边框等）
- 自动生成 QSS 样式表，覆盖所有 UI 元素
- 主题切换即时生效，无需重启

**主题文件格式示例**：

```json
{
  "name": "dark_theme",
  "display_name": "暗黑主题",
  "version": "1.0.0",
  "colors": {
    "background": "#1e1e2e",
    "foreground": "#cdd6f4",
    "accent": "#89b4fa",
    "border": "#45475a"
  }
}
```

#### 4.13.2 主题预览 (`themes/theme_preview.py`)

- `ThemePreviewDialog` — 主题预览对话框，接入 ThemeAwareMixin，深色样式已补齐
- 实时预览主题效果
- 支持主题选择和切换

#### 4.13.3 主题感知混入 (`themes/theme_aware_mixin.py`)

- `ThemeAwareMixin` — 主题感知混入类，UI 组件继承后自动订阅 `theme_changed` 信号
- 组件实现样式更新方法（`_apply_theme(theme)` 或 `_apply_theme_colors(colors)`，取决于组件类型），在主题切换时更新自身样式
- 已集成组件涵盖：Editor、MarkdownPreviewWidget、EditorTabWidget、MinimapWidget、FileTreeWidget、FindReplaceBar、StatusBarWidget、SecretaryWidget、ResourceBar、GameSidebar、ShortcutPanel、ThemePreviewDialog、PluginManagerDialog、CompletionPopup 等

> **注意**：`_apply_theme(theme)` 和 `_apply_theme_colors(colors)` 两种方法在代码中并存，新增组件时应参考同类型组件的实现方式。

### 4.14 存档管理器 (`core/savegame_manager.py`)

从 `Config` 类中拆分出的独立存档管理模块，负责游戏存档的加载和保存。

- `SavegameManager(file_guard, gamedata_dir)` — 存档管理器
- `load()` — 从 `savegame.json` 加载存档
- `save()` — 保存存档，返回 `SavegameSaveResult` 枚举值
- `add_resource(key, amount)` / `get_resources()` — 资源 CRUD
- `check_daily_checkin()` — 每日签到检查，首次启动自动发放奖励（燃料/弹药/钢材/铝材各+100）

**SavegameSaveResult 枚举**：

| 值             | 说明     |
| -------------- | -------- |
| `SUCCESS`      | 保存成功 |
| `WRITE_FAILED` | 写入失败 |

### 4.15 集中式版本管理

版本号以 `src/__init__.py` 中的 `__version__` 为唯一真相源（Single Source of Truth），所有模块和配置文件通过引用获取版本号，而非硬编码。

**版本传播链路**：

```
src/__init__.py (__version__ = "1.8.0")
  ├─→ main.py                    (from src import __version__)
  ├─→ src/main_window.py         (from . import __version__)
  ├─→ src/plugins/plugin_base.py (from .. import __version__ as _app_version)
  │     └─→ PluginMeta.min_app_version 默认值
  ├─→ src/plugins/plugin_sandbox.py (from .. import __version__)
  ├─→ plugins/hello_panzer/main.py  (from src import __version__ as _app_version)
  ├─→ plugins/word_counter/main.py  (from src import __version__ as _app_version)
  └─→ pyproject.toml            (dynamic = ["version"] + attr = "src.__version__")
```

**工具函数**：

- `get_version()` — 返回版本号字符串
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
     → FileOpenService 校验来源（用户/拖放/插件/会话恢复/设置导入）
     → 判断是否笔记库外文件 → config.add_external_file()
     → EditorTabWidget.open_file(filepath)
        → 编码级联检测
        → 判断是否 Markdown → 创建 Editor 或 MarkdownPreviewWidget
        → 生成 tab_id，存入 _tab_info
        → set_file_type() → 绑定语法高亮 + auto_minimap
     → config.add_recent_file()
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
           → 保存最新内容 → shutil.move → 更新 _tab_info
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
pip install PyQt6>=6.8 PyQt6-WebEngine>=6.8 Pygments>=2.19 markdown>=3.8 Pillow>=12.2.0 cryptography>=48.0.0 send2trash>=2.1.0 markdown-it-py>=3.0.0
python main.py
```

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

1. **编码保持**：打开文件时检测编码并记录在 `_tab_info["encoding"]`，保存时使用相同编码
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
12. **文件操作安全**：使用 `FileGuard.safe_read()` / `safe_write()` 替代直接 `open()`，确保文件大小和超时控制
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

22. **主题全局生效**：所有需要响应主题切换的 UI 组件应继承 `ThemeAwareMixin`，实现 `_apply_theme(theme)` 或 `_apply_theme_colors(colors)` 方法。`ThemeAwareMixin` 自动订阅 `theme_changed` 信号
23. **硬编码颜色迁移**：编辑器、Markdown 预览、弹窗中残留的硬编码颜色应逐步迁移到主题 token 系统，迁移方向参考 [color_audit.md](color_audit.md)（VS Code Dark Modern / Dark+）

### 插件约束

24. **可信插件模型**：插件代码运行在主程序进程中，权限系统只限制 PanzerNote 暴露的 API，不是完整安全沙箱。请只安装可信来源的插件
25. **插件 API 边界**：`get_config()` 返回 `ReadOnlyConfigView` 只读视图；`open_file` 走 `FileOpenService.PLUGIN` 路径校验；超时文案诚实说明无法强制终止线程
26. **命令注册原子性**：`PluginAPI.register_command()` 使用 `dict.setdefault()` 原子操作，消除 TOCTOU 竞态条件
27. **MVP_READ_ONLY 实例属性**：`PluginAPI._mvp_read_only` 为实例属性，不可通过类级别篡改

### 性能约束

28. **自动配对性能**：`AutoPairHandlerMixin` 使用 `frozenset` 缓存实现 O(1) 入口过滤，`_doc_char_at()` 替代 `toPlainText()` 全文复制，`_wrap_selection()` 替代 `selectedText()` 大字符串复制。修改 `AUTO_PAIR_CHARS` 字典后缓存自动失效重建
29. **粘贴检测**：`Editor` 重写 `insertFromMimeData()` 设置 `_is_pasting` 标志，`EditorTabWidget._on_text_changed()` 检查此标志跳过粘贴的打字奖励计数。`_PASTE_THRESHOLD = 50`，仅字符增量 ≤50 且非粘贴时计入奖励
30. **MarkdownIt 实例复用**：`MarkdownPreviewWidget._create_md_parser()` 在 `__init__` 中创建一次解析器实例并缓存为 `_md_parser`，`_render_markdown()` 直接调用缓存实例渲染
31. **文件保存异步化**：`SaveTask`（`QRunnable`）+ `SaveTaskSignals`（`QObject`）将 `safe_write` 磁盘 IO 放到 `QThreadPool.globalInstance()` 后台线程执行。保存失败时回滚修改状态并恢复标签页 `*` 标记
32. **Markdown 预览 JS 局部更新**：首次渲染走 `setHtml` 加载完整模板，`loadFinished` 信号触发后标记 `_html_template_loaded = True`，后续渲染通过 `runJavaScript` 仅更新 `innerHTML`。切换文档时自动重置标志。非 WebEngine 模式仍走全量路径。注意：这不是真正 block 级增量渲染
33. **Minimap 块级增量失效**：`MinimapWidget` 改用 `QTextDocument.contentsChange` 信号，精确计算受影响缓存块范围并标记为脏块（`_block_dirty`），仅重新渲染脏块。常规打字仅重绘 1 个块，节省约 95% 渲染开销
34. **状态栏信号驱动统计**：`signal_driven_stats` 默认开启，`characterCount()` 避免全文复制，词数 800ms 防抖，行列号由 `cursorPositionChanged` 驱动
35. **搜索高亮集中管理**：`SearchService` 封装查找/替换，`QTextDocument.find()` 权威光标位置，`ExtraSelectionManager` 统一高亮层，`replace_all` 从后向前逐匹配替换

### 工程约束

36. **快捷键管理**：`ShortcutManager` 已接入 `MenuBuilder`，所有菜单项通过 `manager.register()` 注册，自定义快捷键功能已生效。新增菜单项必须通过 ShortcutManager 注册
37. **错误提示**：使用 `ErrorHandler.show_error()` / `ErrorHandler.show_from_exception()` 替代直接 `QMessageBox`，确保敏感信息过滤和统一分类提示
38. **设置导入校验**：`ConfigImportService` 逐字段校验类型/值范围，非法字段跳过并报告，不直接 `_settings.update()`
39. **集中式版本管理**：`src/__init__.py` 中的 `__version__` 为唯一真相源，所有模块通过 `from src import __version__` 引用。`pyproject.toml` 使用动态版本配置，`scripts/verify_version.py` 提供一致性验证，`main.py` 启动时自动检查
40. **依赖梳理**：`pyproject.toml` 分组 format/dev/all，所有运行时依赖均为必需
41. **增量渲染器命名澄清**：`incremental_renderer.py` 确认为全文 hash 渲染缓存，文档不宣称"真正增量渲染"
42. **分屏语义**：`_split_editor()` 打开新空白文件而非当前文件副本，避免双标签编辑同一文件的数据覆盖风险。菜单文本标注"独立编辑"
43. **封装规范**：禁止通过 `self.config._savegame_manager` 等私有属性访问，使用 `self.config.savegame_manager` 公开属性

---

_本文档基于 PanzerNote v1.8.0 源码整理。版本变更见 [../CHANGELOG.md](../CHANGELOG.md)，未完成规划见 [roadmap.md](roadmap.md)。_
