# PanzerNote v1.6.4 综合技术审阅报告 v2

> **文档版本**：综合版 2.0（在 v1.0 基础上补充对原"未深度审阅"模块的全面检查）
> **审阅基准**：`2026.5.3` 分支（项目 v1.6.4）
> **生成日期**：2026-05-04
> **审阅范围**：项目全部 51 个 Python 源文件、29 个测试文件、全部配置文件
> **报告说明**：本报告整合自 AI-IDE 自动审阅、Claude 第一轮人工审阅、Claude 第二轮深度补充审阅，三份发现交叉去重后，按优先级与类别系统重组

---

## 目录

- [0. 阅读说明](#0-阅读说明)
- [1. 项目概况与架构核对](#1-项目概况与架构核对)
- [2. v2 新增的关键发现](#2-v2-新增的关键发现)
- [3. P0 — 必须立即修复的问题](#3-p0--必须立即修复的问题)
- [4. P1 — 一般问题（建议近期修复）](#4-p1--一般问题建议近期修复)
- [5. P2 — 架构与代码质量改进](#5-p2--架构与代码质量改进)
- [6. P3 — 工程化与配置](#6-p3--工程化与配置)
- [7. 未完成功能模块清单](#7-未完成功能模块清单)
- [8. 可增加的小型功能建议](#8-可增加的小型功能建议)
- [9. 问题总览表](#9-问题总览表)
- [10. 实施路线图](#10-实施路线图)
- [11. 附录：审阅方法与边界](#11-附录审阅方法与边界)

---

## 0. 阅读说明

### 0.1 v2 相对 v1 的变化

v2 补充审阅了 v1 中标记为"未深度审阅"的模块：`editor_actions.py`、`syntax_highlighter.py`、`highlight_themes.py`、`minimap.py`、`file_tree.py`、`editor_settings_dialog.py`、`theme_preview.py`、`shortcut_panel.py`、`shortcut_manager.py`、`menu_builder.py`、`event_bus.py`、`timer_manager.py`、`dpi_helper.py`、`feature_flags.py`、`lazy_loader.py`、`logger.py`、`exceptions.py`、`error_handler.py`、`storage_*.py` 等 19 个模块。

新发现的问题用 `(v2新增)` 标注，便于区分。**部分 v1 结论在 v2 中得到修正**——例如 `FEAT-015 快捷键速查面板入口` 在 v1 中被列为"未绑定"，v2 验证发现**已绑定 Ctrl+/**，所以从新功能列表中删除。

### 0.2 问题编号体系

每个问题分配稳定 ID，便于后续对话或代码注释中引用：

| 前缀    | 类别        | 示例        |
| ------- | ----------- | ----------- |
| `BUG`   | 功能性缺陷  | `BUG-001`   |
| `SEC`   | 安全相关    | `SEC-001`   |
| `PERF`  | 性能问题    | `PERF-001`  |
| `ARCH`  | 架构/设计   | `ARCH-001`  |
| `QUAL`  | 代码质量    | `QUAL-001`  |
| `DOC`   | 文档不一致  | `DOC-001`   |
| `TODO`  | 未完成功能  | `TODO-001`  |
| `FEAT`  | 新功能建议  | `FEAT-001`  |
| `INFRA` | 工程化/配置 | `INFRA-001` |

### 0.3 优先级定义

- **P0**：影响安装、核心功能或数据安全，必须立即修复
- **P1**：实质性影响代码质量、性能或用户体验，建议近期修复
- **P2**：架构改进或长期维护成本相关，可规划性处理
- **P3**：可改进点或新功能建议，按需推进

### 0.4 每条问题的字段

```
### [ID][优先级] 标题
- 位置：文件路径与行号
- 现象/描述：问题表现
- 影响：对用户或代码的实际影响
- 修复方案：具体改动建议
- 难度：低 / 中 / 高
```

---

## 1. 项目概况与架构核对

### 1.1 项目定位

PanzerNote 是一款以《战车少女》（PanzerMaiden）为主题的 PC 端**离线单机记事本程序**，核心理念是"记事本为主、游戏化为灵魂"——通过日常书写积累资源、抽卡建造、点亮图鉴。技术栈为 Python + PyQt5 + Pygments + markdown。

### 1.2 整体架构评价

**优点**：

- `src/` 已按领域分包（core / editor / game / security / plugins / themes / storage / ui / utils），命名清晰
- 测试目录覆盖 29 个核心模块，配套 `benchmarks/` 性能基准目录
- 阶段一到五规划的多数基础设施（日志、异常装饰器、Feature Flag、DPI 帮助器、错误处理器）已落地
- `pyproject.toml` + `requirements.txt` 双轨依赖声明完整
- 插件系统包含完整的 manifest 验证、生命周期管理、热重载支持
- 代码注释详尽，多数模块顶部有文档字符串

**核心问题**：**多处"已完成"模块实际是空架子或名不副实**，v2 补充审阅发现这一现象比 v1 评估的更严重。详见 [§2 v2 新增的关键发现](#2-v2-新增的关键发现)。

### 1.3 文档与代码不一致清单（DOC 类）

下列项目说明文档/README 与代码不一致的事实，是后续 AI 协作的重要风险源：

| ID                   | 项目                  | 文档声称                                         | 代码实际                                                                                                 |
| -------------------- | --------------------- | ------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| `DOC-001`            | Python 版本           | README/项目说明：3.8+                            | `pyproject.toml`: `>=3.11`                                                                               |
| `DOC-002`            | 文件大小上限          | 项目说明：50MB                                   | `config.py:135` 实际 10MB                                                                                |
| `DOC-003`            | `main_window.py` 行数 | 项目说明声称 837                                 | 实际 927                                                                                                 |
| `DOC-004`            | `editor.py` 行数      | 项目说明声称 546                                 | 实际 673                                                                                                 |
| `DOC-005`            | 测试文件数            | 项目说明：27 个                                  | 实际 29 个（新增 `test_feature_flags.py`、`test_virtual_scroll.py`）                                     |
| `DOC-006`            | 虚拟滚动              | 文档：分块加载 + 延迟高亮                        | 实际是一次性 `setPlainText` + 全文 `rehighlight`                                                         |
| `DOC-007`            | 增量渲染              | 文档：行级增量 + LRU + 懒加载                    | 实际只是全文级缓存，`_line_cache` 字段写而不读                                                           |
| `DOC-008`            | 主题系统              | 文档：全局 UI 覆盖                               | 仅覆盖 `main_window` 自身 QSS，下属 29 处独立 `setStyleSheet` 不受影响                                   |
| `DOC-009`            | 存储抽象层            | 文档：已集成                                     | `src/storage/` 685 行无业务调用方                                                                        |
| `DOC-010`            | 插件沙箱              | 文档：插件运行在沙箱环境                         | 仅 `threading.Thread` 包装，无任何 Python 隔离                                                           |
| `DOC-011` _(v2新增)_ | 高 DPI 适配           | 文档：所有 UI 尺寸通过 `dpi_helper.scale()` 计算 | 启用 `AA_EnableHighDpiScaling` 后 dpi_helper 永久返回 1.0，整个模块是 no-op                              |
| `DOC-012` _(v2新增)_ | 懒加载                | 文档：非核心模块按需加载                         | `LazyLoader.register/get/add_deferred_init/run_deferred_inits` 无任何调用方，只有 `StartupProfiler` 在用 |
| `DOC-013` _(v2新增)_ | 统一异常处理装饰器    | 文档：全项目使用 @safe_call                      | 实际仅 `config.py` 中 8 处使用，其余仍是裸 try/except                                                    |
| `DOC-014` _(v2新增)_ | 快捷键自定义          | 文档：用户可自定义并保存                         | ShortcutManager 实例化后从未调用过 register()，自定义快捷键无法生效                                      |
| `DOC-015` _(v2新增)_ | 主题数                | 文档：内置浅色和深色                             | theme_engine 是浅+深，但 highlight_themes 只有 1 个（pycharm_light），两者不联动                         |

---

## 2. v2 新增的关键发现

v2 补充审阅最重大的发现集中在以下几点，**这些都是 v1 因未深读相应模块而漏报的问题**：

### 2.1 ShortcutManager 完全空运转（严重）

ShortcutManager 类、ShortcutPanel 类、ShortcutEditDialog 类共 600+ 行代码，提供了完整的快捷键注册、冲突检测、自定义保存功能。**但 MainWindow 实例化它后从未调用过 `register()` 方法**。这意味着：

- 用户在快捷键面板中看到的列表只是 `_DEFAULT_SHORTCUTS` 静态字典，不反映任何运行时状态
- 用户"自定义快捷键"功能完全失效——保存到 settings 但 QAction 不会更新
- ShortcutManager 启动时会输出 9 条系统冲突警告（Ctrl+C/V/X/A/Z/Y/S/F/Alt+F4 与系统快捷键的"伪冲突"）

详见 `BUG-013`、`BUG-014`、`BUG-015`。

### 2.2 dpi_helper 在生产环境是 no-op（严重）

`main.py:33` 启用了 `AA_EnableHighDpiScaling=True`，而 dpi_helper 的 `init_dpi()` 第 46-49 行：

```python
if app.testAttribute(Qt.AA_EnableHighDpiScaling):
    _scale_factor = 1.0
    _initialized = True
    return
```

直接 `_scale_factor = 1.0` 然后 return。这意味着整个 dpi_helper 161 行代码、所有 `scale()`/`scale_size()`/`scale_font()`/`scale_stylesheet()` 调用**都是 no-op**——它们只是把输入数值原样返回。详见 `ARCH-008`。

### 2.3 LazyLoader 是空架子（中等）

`src/utils/lazy_loader.py` 的 `LazyLoader` 类（45 行核心逻辑）实现了 register / get / add_deferred_init / run_deferred_inits，但 grep 全项目无任何调用方。仅 `StartupProfiler` 被用来记录启动各阶段耗时。详见 `ARCH-009`。

### 2.4 MenuBuilder 与 ShortcutManager 各管一套快捷键（架构性矛盾）

- `MenuBuilder` 在构建菜单时直接 `action.setShortcut(QKeySequence("Ctrl+S"))`
- `_DEFAULT_SHORTCUTS` 也定义了 `"file.save": ("保存", "Ctrl+S", "文件")`

两套并存，且 MenuBuilder 这套**不与 ShortcutManager 联动**——用户的自定义不影响菜单项快捷键。详见 `ARCH-010`。

### 2.5 file_tree 删除文件不进回收站（数据安全）

`src/editor/file_tree.py:404-408` 直接 `shutil.rmtree(filepath)` / `os.remove(filepath)`。误删后无法恢复。详见 `BUG-016`。

### 2.6 plugin_manager 热重载失效（功能性 bug）

`reload_plugin` 第 152 行清理 `sys.modules[f"plugins.{plugin_id}"]`，但 `_import_plugin` 第 240 行注册的是 `f"panzernote_plugin_{os.path.basename(plugin_path)}"`。**两个名字永远不一致**，旧版本永远不会被清理，热重载实际无效。详见 `BUG-017`。

### 2.7 stats_timer 500ms 高频轮询（性能浪费）

`src/core/timer_manager.py:60-62`：`stats_timer.setInterval(500)`，每秒 2 次拉取编辑器字符数、行号、列号刷新状态栏。但光标位置变化通常每秒最多 5-10 次，**应改为信号驱动**而非轮询。详见 `PERF-002`。

### 2.8 ErrorHandler 敏感信息正则会误伤（中等）

`src/utils/error_handler.py:78` 的 `re.compile(r'key\s*[=:]\s*\S+', re.IGNORECASE)` 会误伤 `mkkey: not found` 这类正常错误信息（命中 `key: not`，把 `not found` 识别为密钥）。详见 `QUAL-016`。

---

## 3. P0 — 必须立即修复的问题

### 3.1 安装/构建相关

#### `INFRA-001` [P0] `pyproject.toml` 的 build-backend 字符串无效

- **位置**：`pyproject.toml`，第 3 行
- **现象**：

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.backends._legacy:_Backend"   # ← 错误
```

- **影响**：`setuptools.backends._legacy` 这个模块**在任何版本的 setuptools 中都不存在**。任何 `pip install -e .`、`python -m build`、或基于 PEP 517 的安装都会立即抛 `ModuleNotFoundError: No module named 'setuptools.backends'`。该字符串疑似 AI 生成时编造。
- **修复方案**：

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"
```

- **难度**：低（5 分钟）

### 3.2 功能性 bug

#### `BUG-001` [P0] `_reset_settings()` 用户点"确定"后什么都不做

- **位置**：`src/main_window.py` 第 725-738 行
- **现象**：

```python
def _reset_settings(self):
    msg_box = QMessageBox(self)
    msg_box.setWindowTitle("确认")
    msg_box.setText("确定要恢复所有设置为默认值吗？")
    ...
    msg_box.exec_()
    if msg_box.clickedButton() == yes_btn:
        pass   # ← 用户点"确定"后什么都不做
```

- **影响**：用户点"恢复默认"，看到确认弹窗，点"确定"后毫无反应。属于**直接欺骗用户**的功能性 bug。
- **修复方案**：调用 `config.reset_to_defaults()`（需新增），重新加载 settings 到 DEFAULT_SETTINGS，并刷新所有受影响的 UI 组件（编辑器字体、行号、缩略图、自动保存间隔等）。
- **难度**：中（30 分钟，含 UI 刷新）

#### `BUG-002` [P0] `open_file` 编码检测缩进错误

- **位置**：`src/editor/editor_tabs.py` 第 329-337 行
- **现象**：UTF-16 检测的 `try` 块多了一层缩进（应该 4 空格层级，实际 8 空格）：

```python
except UnicodeDecodeError:
    try:
        content = file_guard.safe_read(filepath, encoding='gbk', ...)
        detected_encoding = "GBK"
    except UnicodeDecodeError:
            try:                                          # ← 多余缩进
                content = file_guard.safe_read(filepath, encoding='utf-16', ...)
```

- **影响**：语法上合法（嵌套 try 仍能工作），但属于复制粘贴错误，体现代码审查不严。维护时容易引发误读。
- **修复方案**：把 UTF-16 检测的 `try` 块缩进对齐到与上层 `try` 同级。
- **难度**：低（5 分钟）

#### `BUG-003` [P0] 搜索框拒绝合法输入

- **位置**：`src/security/input_validator.py` 第 52-58 行 + `src/editor/find_replace.py` 第 327-329 行
- **现象**：搜索框对输入内容做"危险模式"匹配，模式包括 `<script>`、`javascript:`、`onclick=`、`data:text/html`、`vbscript:`。但**搜索框搜的是用户自己的本地文本，不存在 XSS 注入语义**。验证逻辑实际验证：

| 输入                      | 当前行为                     | 期望行为 |
| ------------------------- | ---------------------------- | -------- |
| `onclick="foo()"`         | **拒绝**                     | 应允许   |
| `onChange={handle}`       | **拒绝**（命中 `on\w+\s*=`） | 应允许   |
| `javascript:void(0)`      | **拒绝**                     | 应允许   |
| `<script src="main.js">`  | **拒绝**                     | 应允许   |
| `Add data:text/html link` | **拒绝**                     | 应允许   |

- **影响**：前端开发者在自己的 HTML/JS 笔记里搜索任何含上述关键字的字符串都会**静默失败**——`_build_pattern` 直接返回 `None`，状态栏显示"0 个匹配"。基本相当于禁用搜索功能。
- **修复方案**：删除 `find_replace.py:327-329` 的 `validator.validate_search(query)` 调用，仅保留长度限制。
- **难度**：低（30 分钟，含简单回归测试）

#### `BUG-004` [P0] 9 个菜单项是空函数（用户点击无反馈）

- **位置**：`src/main_window.py`
- **现象**：以下 9 个菜单项绑定的处理函数全部是 `pass`：

| 菜单项                   | 函数                       | 行号                  |
| ------------------------ | -------------------------- | --------------------- |
| 游戏 → 导入角色数据...   | `_import_characters`       | 633                   |
| 游戏 → 导入外部文档...   | `_import_document`         | 637                   |
| 游戏 → 统计 → 打字统计   | `_show_typing_stats`       | 641                   |
| 游戏 → 统计 → 建造记录   | `_show_construction_stats` | 645                   |
| 游戏 → 统计 → 图鉴完成度 | `_show_collection_stats`   | 649                   |
| 设置 → 游戏设置          | `_show_game_settings`      | 718                   |
| 设置 → 恢复默认          | `_reset_settings` 内部     | 738（参见 `BUG-001`） |
| 帮助 → 新手攻略          | `_show_guide`              | 744                   |
| 帮助 → 使用说明          | `_show_manual`             | 748                   |

- **影响**：用户点击后**完全无反馈**——既不弹错误也不提示"功能开发中"。同属此类的还有 `game_view_container` 切换到建造/车库/图鉴视图后显示空白容器（`main_window.py` `_switch_view` 第 549-565 行）。
- **修复方案（最低限度）**：所有未实现的函数显式弹出"功能开发中"提示。视图容器添加占位标签。
- **难度**：低（1 小时全部完成）

#### `BUG-005` [P0] 版本号硬编码三处，未引用 `src.__version__`

- **位置**：
  - `main.py:38` —— `app.setApplicationVersion("1.6.4")`
  - `main.py:69` —— `logger.info("PanzerNote 启动，版本 1.6.4")`
  - `src/main_window.py` 第 849 行附近（关于对话框） —— 字符串硬编码版本号
- **现象**：`src/__init__.py:6` 已经定义了 `__version__ = "1.6.4"`，且 `plugin_sandbox.py:79` 已正确使用，但其他三处仍硬编码字符串。
- **影响**：版本升级时极易遗漏，导致不同显示位置版本号不一致。
- **修复方案**：所有版本号引用统一使用 `from src import __version__`。
- **难度**：低（15 分钟）

### 3.3 数据安全相关

#### `SEC-001` [P0] Markdown 预览启用了原始 HTML

- **位置**：`src/editor/markdown_preview.py:500`
- **现象**：

```python
md = _MarkdownIt("commonmark", {"html": True})   # ← raw HTML 启用
```

且 python-markdown 默认也保留原始 HTML 标签。

- **影响**：恶意 .md 文件可包含：
  - `<script>` 标签 —— 在 QWebEngineView 中**会执行 JavaScript**
  - `<iframe src="...">` —— 加载远程内容
  - `<img src="file:///..." onerror="...">` —— 探测本地文件存在性

  考虑用户离线使用场景：恶意 .md 来源主要是从聊天/邮件/网页下载的 README 或克隆的项目文档，**可被实际利用**。

- **修复方案**：

```python
md = _MarkdownIt("commonmark", {"html": False})
```

python-markdown 端可使用 `bleach` 或 `nh3` 库做 HTML 净化（可选添加为依赖）。

- **难度**：低（5 分钟改字面量；若需 HTML 净化库 1 小时）

#### `SEC-002` [P0] 本地图片路径解析未走 `PathValidator`

- **位置**：`src/editor/markdown_preview.py:528-557` 的 `_resolve_local_images`
- **现象**：

```python
abs_path = os.path.normpath(os.path.join(self._base_path, src))
if os.path.exists(abs_path):       # ← 仅检查存在，未做白名单/穿越校验
    file_url = QUrl.fromLocalFile(abs_path).toString()
```

- **影响**：恶意 .md 含 `![](../../../../Windows/win.ini)` 会被解析为 `file:///C:/Windows/win.ini` 并加载。即使最终 Pixmap 解析失败，仍会触发文件读取（构成存在性探测）。
- **修复方案**：在 `_resolve_src` 中调用 `PathValidator.is_path_safe(abs_path)`，或更严格：仅允许 `_base_path` 子目录下的相对路径，绝对路径与穿越路径直接拒绝。
- **难度**：低（1 小时）

#### `SEC-003` [P0] 加密存档可能被默认数据覆写

- **位置**：`src/core/config.py:229-240`
- **现象**：

```python
if self._crypto_manager.is_encrypted():
    try:
        if self._encryption_password:
            self._savegame = self._crypto_manager.decrypt_savegame(...)
        else:
            self._savegame = self.DEFAULT_SAVEGAME.copy()   # ← 危险路径
            get_logger(__name__).info("存档已加密，需要密码才能解密")
    except DecryptionError as e:
        ...
        self._savegame = self.DEFAULT_SAVEGAME.copy()
```

后续若调用 `save_savegame()` 而无解密保护守卫，会用默认数据**覆写真实加密存档**。

- **影响**：用户启用加密后未输密码的会话中，若程序自动调用了存档保存（如挂机定时器、退出时自动 save），**真实存档被默认值覆写、玩家进度归零**。
- **修复方案**：增加 `_savegame_encrypted_unread: bool` 标志位，未解锁状态下 save_savegame 直接 return。
- **难度**：中（1-2 小时，含测试）

### 3.4 核心功能未接入

#### `TODO-001` [P0] 打字奖励核心逻辑未接入 `textChanged`

- **位置**：`src/core/config.py`、`src/main_window.py`、`src/editor/editor_tabs.py`
- **现象**：
  - `config.py` 已有 `today_chars_typed` / `total_chars_typed` / `daily_typing_limit`
  - `main_window._update_stats()` 已读取 `today_chars_typed` 显示在资源栏
  - 但 `editor_tabs._on_text_changed` **从未调用任何字符计数逻辑**
- **影响**：项目核心理念"通过书写获取资源"的关键链路缺失。
- **修复方案**：
  1. 在 `editor_tabs.py` 的 `_on_text_changed` 中，结合 `info["last_saved_chars"]` 计算新增字符数（仅计正向变化）
  2. 区分手动输入与粘贴/撤销
  3. 通过新增信号 `chars_typed(count)` 传递到 `MainWindow`
  4. `MainWindow` 调用 `config.add_chars_typed(count)`，到达阈值时触发资源奖励
  5. 实现递减收益算法：

  $$
  r(n) = \begin{cases} 1.0 & n \le 1000 \\ 0.4 & 1000 < n \le 3000 \\ 0.1 & n > 3000 \end{cases}
  $$

- **难度**：中（1-2 小时核心逻辑 + 1 小时测试）

### 3.5 v2 新增的 P0

#### `BUG-013` [P0] _(v2新增)_ ShortcutManager 实例化后从未注册过任何动作

- **位置**：`src/main_window.py:60`、`src/core/shortcut_manager.py`
- **现象**：

```python
# main_window.py
self.shortcut_manager = ShortcutManager(config)   # 第 60 行，实例化
self.shortcut_panel = ShortcutPanel(self.shortcut_manager, self)  # 第 194 行
# 从未调用 self.shortcut_manager.register(...)
```

ShortcutManager 提供了完整的 `register(action_id, name, default_shortcut, callback, category)` 接口，但 MainWindow 没有为任何菜单项调用它。所有菜单的 QAction 由 MenuBuilder 直接创建并 setShortcut。

- **影响**：
  - **用户在快捷键面板中"自定义快捷键"功能完全无效**——`_save_custom_shortcuts` 写入 settings.shortcuts，但实际菜单 QAction 并不会重新读取
  - 快捷键面板显示的列表是 `_DEFAULT_SHORTCUTS` 静态字典，不反映实际 QAction 状态
  - 600+ 行代码（ShortcutManager 340 行 + ShortcutPanel 292 行）实质等于装饰品
- **修复方案**：
  - **方案 A（推荐）**：MainWindow 改为通过 ShortcutManager 注册所有菜单动作，MenuBuilder 接受 ShortcutManager 实例并使用 `manager.get_action(action_id)` 加到菜单。这是真正"快捷键可定制"的实现路径
  - **方案 B（保守）**：移除 ShortcutManager 整套自定义功能，ShortcutPanel 改为只读展示菜单上已绑定的快捷键
- **难度**：高（方案 A 1-2 天）/ 中（方案 B 半天）

#### `BUG-014` [P0] _(v2新增)_ 快捷键启动时报 9 条系统冲突警告

- **位置**：`src/core/shortcut_manager.py:43-60`、`80-115`
- **现象**：`_SYSTEM_SHORTCUTS` 把 Ctrl+C/V/X/A/Z/Y/S/F/Alt+F4 标记为"系统快捷键"，而 `_DEFAULT_SHORTCUTS` 同时把 `edit.copy = "Ctrl+C"` 等动作绑定到这些快捷键。`register()` 方法第 181-186 行的 `check_conflicts` 会检测到冲突并 `_logger.warning`：

```python
if conflicts:
    self._logger.warning(
        "快捷键冲突: %s -> %s (冲突项: %s)",
        action_id, key_seq, conflicts
    )
```

- **影响**：虽然现在因 `BUG-013`（register 没被调用）这些 warning 不会真的触发，但**修复 BUG-013 之后会立即产生 9 条警告日志**：

```
快捷键冲突: file.save -> Ctrl+S (system: 系统保存)
快捷键冲突: edit.undo -> Ctrl+Z (system: 系统撤销)
快捷键冲突: edit.redo -> Ctrl+Y (system: 系统重做)
快捷键冲突: edit.cut -> Ctrl+X (system: 系统剪切)
快捷键冲突: edit.copy -> Ctrl+C (system: 系统复制)
快捷键冲突: edit.paste -> Ctrl+V (system: 系统粘贴)
快捷键冲突: edit.select_all -> Ctrl+A (system: 系统全选)
快捷键冲突: edit.find -> Ctrl+F (system: 系统查找)
快捷键冲突: file.exit -> Alt+F4 (system: 系统关闭窗口)
```

逻辑性错误：编辑器需要 Ctrl+C/V/X/A/Z 是天经地义的，绝不应该报告为"冲突"。

- **修复方案**：把 `_SYSTEM_SHORTCUTS` 重新定义为"操作系统全局保留快捷键，应用不可覆盖"，**仅保留** `Win+D`、`Win+E`、`Win+L`、`Ctrl+Alt+Delete`、`Alt+Tab`。常规编辑快捷键（Ctrl+C/V/X 等）从该列表移除。
- **难度**：低（10 分钟）

---

## 4. P1 — 一般问题（建议近期修复）

### 4.1 安全问题

#### `SEC-004` [P1] 插件沙箱不是真正的沙箱

- **位置**：`src/plugins/plugin_sandbox.py`
- **现象**：自称"沙箱"，但仅是 `threading.Thread(daemon=True)`：
  - 插件可 `import os; os.system(...)` 执行任意命令
  - 插件可 `import sys; sys.modules['src.core.config']._savegame['cores'] = 99999` 修改存档
  - `MVP_READ_ONLY = True` 是类变量，插件首行 `PluginAPI.MVP_READ_ONLY = False` 即可绕过权限检查
- **影响**：**文档承诺虚假**。Python 在不引入子进程隔离、RestrictedPython 或容器的情况下，无法真正沙箱化第三方代码。
- **修复方案**：
  - **短期（半天）**：把"沙箱"重命名为"插件包装器"，文档改为"提供异常保护和 API 约定，不防御恶意插件"
  - **长期（2-3 天）**：插件改为独立子进程，用 `multiprocessing` + `Pipe` 通信
- **难度**：低（短期）/ 高（长期方案）

#### `SEC-005` [P1] `path_validator` 含死代码与重复正则

- **位置**：`src/security/path_validator.py:41-47`、`105-111`
- **现象**：

```python
_TRAVERSAL_PATTERNS = [
    re.compile(r'\.\.[/\\]'),       # 第 42 行
    re.compile(r'\.\.[/\\]'),       # 第 43 行 ← 与上一行完全相同
    ...
]

# 第 105-111 行：
try:
    real = os.path.realpath(path)
    abs_path = os.path.abspath(path)
    if real != abs_path:
        pass        # ← 检测到符号链接但什么都不做
except (OSError, ValueError):
    pass
```

- **修复方案**：删除重复的第 43 行；`pass` 改为 `return True`（视符号链接为穿越）。
- **难度**：低（30 分钟）

#### `SEC-006` [P1] `MAX_PATH_LENGTH = 260` 过于严格

- **位置**：`src/security/path_validator.py:39`
- **现象**：硬编码 Windows 短路径上限 260。文档同时声称处理 Windows `\\?\` 长路径前缀，自相矛盾。
- **修复方案**：调到 4096：

```python
MAX_PATH_LENGTH = 4096
```

- **难度**：低（5 分钟）

#### `SEC-007` [P1] 多处 `QMessageBox` 直接显示原始异常字符串

- **位置**：`src/editor/editor_tabs.py`、`src/main_window.py`、`src/editor/file_tree.py:342, 361, 411` 等多处 `QMessageBox.critical/warning(..., str(e))`
- **现象**：项目已实现 `ErrorHandler.show_from_exception()` 含敏感信息过滤，但实际错误对话框仍直接拼接 `str(e)`，未走过滤层。
- **影响**：异常字符串可能含完整文件路径、堆栈、内部状态等信息，构成轻度信息泄露。
- **修复方案**：将所有 `QMessageBox.critical/warning(self, "错误", str(e))` 改为 `ErrorHandler.show_from_exception(self, e, category=ErrorCategory.FILE)`。
- **难度**：中（1-2 小时，约 10 处替换）

### 4.2 性能与稳定性

#### `PERF-001` [P1] `_on_text_changed` 大文件性能差

- **位置**：`src/editor/editor_tabs.py:761-762`
- **现象**：

```python
current_content = editor.toPlainText()                                # ← 拉取整个文本
if current_content != info.get("last_saved_content", ""):             # ← 完整字符串比较
```

- **影响**：每次按键复制整个文档文本 + 字符串比较。1MB 笔记下打字明显卡顿。
- **修复方案**：用 Qt 自带的 `QTextDocument.isModified()` 标志位替代字符串比较。
- **难度**：中（1 小时）

#### `PERF-002` [P1] _(v2新增)_ `stats_timer` 500ms 高频轮询

- **位置**：`src/core/timer_manager.py:60-62`
- **现象**：

```python
self.stats_timer = QTimer(self)
self.stats_timer.setInterval(500)         # ← 每 500ms 一次
self.stats_timer.timeout.connect(self._handle_update_stats)
self.stats_timer.start()
```

`_update_stats` 实际工作是从 editor 拉取字符数、行号、列号刷新状态栏。

- **影响**：
  - 即使用户没有操作，每秒也会触发 2 次 UI 刷新
  - 高频轮询消耗少量 CPU 但增加电池消耗（笔记本场景）
  - 用户敲一个键到状态栏更新最长延迟 500ms（不流畅）
- **修复方案**：改为信号驱动：
  - 监听 `QTextEdit.cursorPositionChanged` 更新行/列
  - 监听 `QTextDocument.contentsChanged` 更新字符数（含轻量节流，如 100ms 内只更新一次）
  - 仅保留低频的资源栏刷新（如 5 秒一次，因为挂机奖励是分钟级）
- **难度**：中（1-2 小时）

#### `BUG-006` [P1] `save_all` 中对未命名文件触发对话框导致标签闪烁

- **位置**：`src/editor/editor_tabs.py:492-518`（`save_all` 方法）
- **现象**：保存所有文件时，对未命名文件会调用 `save_current_as()` 弹对话框，**循环中反复切换当前标签** 弹窗。
- **修复方案**：先收集所有未命名文件 → 保存已命名的 → 最后逐个处理未命名（不切换标签）。
- **难度**：中（30 分钟）

#### `BUG-007` [P1] `_save_user_data_path` 用裸 `open()` 而非 FileGuard

- **位置**：`src/core/config.py:163-166`
- **现象**：项目其他 JSON 读写都走 `FileGuard.safe_read/safe_write`，但 `user_data_path.txt` 的读写直接用 `open()`，绕过了大小限制和超时控制。
- **修复方案**：改用 FileGuard 并设 `validate_path=False`。
- **难度**：低（20 分钟）

#### `BUG-008` [P1] `bauxite_counter` 存放在 settings 而非 savegame

- **位置**：`src/game/game_engine.py:30`、`src/core/config.py` DEFAULT_SETTINGS
- **现象**：`bauxite_counter` 是游戏运行时状态，存储在 `settings.json` 而非 `savegame.json`。
- **影响**：用户点"恢复默认设置"会重置该计数器；语义混乱。
- **修复方案**：迁移到 `savegame`，提供向后兼容（首次启动时若发现 settings 中有则迁移）。
- **难度**：低（20 分钟）

#### `BUG-009` [P1] `async_highlight` 返回值类型不一致

- **位置**：`src/editor/async_highlight.py:79-109`
- **现象**：`render` 方法在三种路径下返回值语义完全不同：feature flag 关闭返回 HTML 字符串、缓存命中返回 HTML、正常路径返回 task_id。调用方拿到字符串后无法区分。
- **影响**：`markdown_preview.py:603-610` 把返回值赋给 `self._pending_async_task`，缓存命中时这个"task_id"实际是大段 HTML，后续 `cancel(self._pending_async_task)` 会查找 `_active_workers[那段HTML]`——一个非常隐蔽的潜在 bug。
- **修复方案**：拆为 `render_sync()` 返回 HTML 和 `render_async()` 返回 task_id 两个方法。
- **难度**：中（2-3 小时）

#### `BUG-010` [P1] `config.py` 默认 `max_file_size = 10MB` 与文档声称的 50MB 不一致

- **位置**：`src/core/config.py:135`
- **修复方案**：把限制提到 50MB（与文档一致），并在错误对话框中显式告知当前限制值与如何调整。
- **难度**：低（10 分钟）

#### `BUG-011` [P1] 日志警告刷屏：`is_path_in_whitelist`

- **位置**：`src/security/path_validator.py:138-140`
- **现象**：每次合法但不在白名单的路径访问都会触发 `WARNING` 日志。
- **修复方案**：降级为 `DEBUG`。
- **难度**：低（5 分钟）

#### `BUG-016` [P1] _(v2新增)_ file_tree 删除文件不进回收站

- **位置**：`src/editor/file_tree.py:404-408`
- **现象**：

```python
if msg_box.clickedButton() == yes_btn:
    try:
        if is_dir:
            import shutil
            shutil.rmtree(filepath)
        else:
            os.remove(filepath)
```

直接物理删除，**误删后无法恢复**。

- **影响**：用户在文件树右键删除笔记或文件夹后，文件**永久从磁盘消失**。这是单机记事本应用最危险的数据风险点之一。
- **修复方案**：使用 `send2trash` 库（约 200KB，零依赖）发送到操作系统回收站：

```python
try:
    from send2trash import send2trash
    send2trash(filepath)
except ImportError:
    # 降级方案：移到 .trash 子目录而不是直接删除
    import shutil, time
    trash_dir = os.path.join(self.config.get_notebooks_path(), ".trash")
    os.makedirs(trash_dir, exist_ok=True)
    timestamp = int(time.time())
    target = os.path.join(trash_dir, f"{os.path.basename(filepath)}.{timestamp}")
    shutil.move(filepath, target)
```

并在 `requirements.txt` 添加 `send2trash`。

- **难度**：低（30 分钟）

#### `BUG-017` [P1] _(v2新增)_ plugin_manager 热重载失效

- **位置**：`src/plugins/plugin_manager.py:151-153`、`240`
- **现象**：

```python
# 第 240 行：实际加载时使用的模块名
module_name = f"panzernote_plugin_{os.path.basename(plugin_path)}"

# 第 151-153 行：reload_plugin 中清理时使用的模块名
module_name = f"plugins.{plugin_id}"
if module_name in sys.modules:
    del sys.modules[module_name]
```

**两个 `module_name` 永远不一致**。`del sys.modules[...]` 找不到模块，旧版本永远残留在 `sys.modules` 中。

- **影响**：用户在插件管理对话框点"重载"，实际看似工作（因为 `_import_plugin` 会创建新的 module 对象），但旧的 module_name 会一直累积在 `sys.modules` 中，造成内存泄漏；如果插件相互 import，老引用还会被持有。
- **修复方案**：

```python
def reload_plugin(self, plugin_id: str) -> PluginBase:
    was_activated = (...)
    self.unload_plugin(plugin_id)

    # 修正：使用与 _import_plugin 一致的 module_name
    plugin_dir = self._find_plugin_dir(plugin_id)
    module_name = f"panzernote_plugin_{os.path.basename(plugin_dir)}"
    if module_name in sys.modules:
        del sys.modules[module_name]

    plugin = self.load_plugin(plugin_id)
    if was_activated:
        self.activate_plugin(plugin_id)
    return plugin
```

- **难度**：低（30 分钟）

### 4.3 性能优化的"虚假实现"

#### `ARCH-001` [P1] `VirtualScrollManager` 名不副实

- **位置**：`src/editor/virtual_scroll.py:48-77`
- **现象**：注释声称"分块加载"，但 `setPlainText(content)` 是一次性塞入完整内容；然后立即 `rehighlight()` 全文。"延迟高亮"被 `rehighlight()` 抵消。
- **修复方案**：要么真正实现分块加载，要么删除 `rehighlight()` 调用并重命名为 `LazyHighlightManager`。
- **难度**：低（重命名 + 删除 1 行）/ 高（真正分块）

#### `ARCH-002` [P1] `IncrementalRenderer` 名不副实

- **位置**：`src/editor/incremental_renderer.py`
- **现象**：`_detect_changes` 只返回 boolean，任何变化触发全文渲染。`_line_cache` 字段在第 59、84、86、102 行只写不读，是死代码。
- **修复方案**：改名为 `RenderCache`，删除 `_line_cache` 字段。
- **难度**：低

#### `QUAL-001` [P1] `async_highlight` LRU 实现实际是 FIFO

- **位置**：`src/editor/async_highlight.py:154-156`
- **现象**：`oldest = list(self._results_cache.keys())[0]` 是 FIFO 不是 LRU。
- **修复方案**：用 `collections.OrderedDict`，命中时 `move_to_end(key)`；或用 `functools.lru_cache`。
- **难度**：低（30 分钟）

### 4.4 文档与版本不一致

`DOC-001` ~ `DOC-015` 已在 [§1.3](#13-文档与代码不一致清单doc-类) 列出。具体修复见 [§10 实施路线图](#10-实施路线图)。

### 4.5 代码质量

#### `QUAL-002` [P1] `config.py` 中 5 个 `get_*_setting` 方法逻辑重复

- **位置**：`src/core/config.py:361-413`
- **现象**：`get_editor_setting` / `get_game_setting` / `get_secretary_setting` / `get_view_setting` / `get_window_setting` 五个方法逻辑完全相同。
- **修复方案**：

```python
def _get_ns_setting(self, namespace: str, key: str, default=None):
    return self._settings.get(namespace, {}).get(key, default)

def get_editor_setting(self, key, default=None):
    return self._get_ns_setting("editor", key, default)
```

- **难度**：低（30 分钟）

#### `QUAL-003` [P1] `main_window.py` 仍过长（927 行）

- **位置**：`src/main_window.py`
- **现象**：包含大量编辑代理方法、内联的插件管理对话框（约 120 行）、视图切换等多种职责。
- **修复方案**：
  - 插件管理对话框提取为 `src/plugins/plugin_manager_dialog.py`
  - 编辑代理方法合并到 `EditorActionsMixin`
- **难度**：中

#### `QUAL-004` [P1] 插件管理对话框关闭重开模式

- **位置**：`src/main_window.py:854-907`
- **现象**：6 个 `_on_xxx`（load/activate/deactivate/unload/reload）每个都执行 `dialog.accept(); self._show_plugin_manager()`，**关闭再重开对话框**。
- **影响**：闪烁；用户当前选择丢失；操作下一个插件需要重新滚动选中。
- **修复方案**：保持对话框打开，改为内部刷新 `list_widget`。
- **难度**：低（1 小时）

#### `QUAL-005` [P1] `_show_plugin_manager` 在方法内部重复导入 PyQt5 组件

- **位置**：`src/main_window.py:810-813`
- **现象**：方法内部重新 import `QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QLabel, QGroupBox`，前三者已在文件顶部导入，后五者未在顶部导入。
- **修复方案**：把所有需要的 Qt 组件统一在文件顶部导入。
- **难度**：低（10 分钟）

#### `QUAL-006` [P1] `editor_tabs._get_editor_from_widget` 在批量操作中反复调用

- **位置**：`src/editor/editor_tabs.py` 多处批量方法
- **修复方案**：抽出 `_iter_editors()` 辅助方法。
- **难度**：低（30 分钟）

#### `QUAL-007` [P1] `CryptoManager` 用 `".."` 相对路径定位 savegame

- **位置**：`src/security/crypto_manager.py:36`
- **现象**：`os.path.join(config_dir, "..", "gamedata", "savegame.json")` 解析依赖 config_dir 形态。
- **修复方案**：构造函数显式接受 `savegame_dir` 参数。
- **难度**：低（20 分钟）

#### `QUAL-016` [P1] _(v2新增)_ ErrorHandler 敏感信息过滤正则会误伤

- **位置**：`src/utils/error_handler.py:78`
- **现象**：

```python
re.compile(r'key\s*[=:]\s*\S+', re.IGNORECASE)
```

- **影响**：测试用例：

| 输入                        | 当前行为                                                     | 期望       |
| --------------------------- | ------------------------------------------------------------ | ---------- |
| `mkkey: not found`          | 误判为密钥（`key: not found` 命中），输出 `mk[已过滤] found` | 应保持原文 |
| `on line 10`                | `line 10` 被识别为堆栈，输出 `on [已过滤]`                   | 应保持原文 |
| `处理第 5 行 line 5 时出错` | 输出 `处理第 5 行 [已过滤] 时出错`                           | 应保持原文 |

很多正常的错误消息会被过度过滤，最终用户看到的是有大量"[已过滤]"的提示，反而难以理解。

- **修复方案**：让正则更严格：

```python
# 仅当 key/password/token 等关键字位于行首或紧跟空格/逗号时才匹配
re.compile(r'(?:^|\s)(password|token|secret|api[-_]?key)\s*[=:]\s*[\S]+', re.IGNORECASE)
# line N 仅当出现在 File "..." 后才视为堆栈
re.compile(r'File\s+"[^"]*",\s*line\s+\d+')
```

- **难度**：低（30 分钟）

#### `QUAL-017` [P1] _(v2新增)_ JSON 格式化忽略缩进设置

- **位置**：`src/editor/editor_actions.py:237`
- **现象**：

```python
formatted = json.dumps(parsed, ensure_ascii=False, indent=4)
```

`indent=4` 硬编码，不读取 `editor.tab_width` 设置（如果有）。

- **修复方案**：从 config 读取 `code_indent_size`（如已存在），或新增此设置项；若没有则保持 4，但用常量代替魔数：

```python
INDENT_SIZE = self.config.get_editor_setting("code_indent_size", 4) if hasattr(self, "config") else 4
formatted = json.dumps(parsed, ensure_ascii=False, indent=INDENT_SIZE)
```

- **难度**：低（20 分钟）

#### `QUAL-018` [P1] _(v2新增)_ `format_document` 不支持的文件类型静默无反馈

- **位置**：`src/editor/editor_actions.py:230-269`
- **现象**：`format_document` 只支持 JSON / XML / HTML 三种 `_file_type`。如果当前是 YAML / TOML / CSS / Python 等其他文件，调用快捷键后**完全静默不做事**。
- **修复方案**：添加 else 分支：

```python
else:
    QMessageBox.information(
        self, "格式化",
        f"暂不支持 {self._file_type} 文件的格式化。\n"
        f"已支持：JSON、XML、HTML。"
    )
```

- **难度**：低（10 分钟）

#### `QUAL-019` [P1] _(v2新增)_ `safe_call` 装饰器使用率极低

- **位置**：全项目（仅 `config.py` 中 8 处使用）
- **现象**：`@safe_call` 装饰器在 `src/utils/exceptions.py` 实现完整，包含 `default`、`show_error`、`reraise`、`catch`、`log_level` 等参数，但全项目仅 8 处使用。其他地方仍是裸 `try/except` 或 `except Exception: pass`。
- **影响**：阶段一规划的"统一异常处理"目标未达成。
- **修复方案**：分批替换：
  - 第一批（高价值）：所有"silent except"（如 `auto_pair_handler` 的 6 处、`feature_flags._save` 等）改为 `@safe_call(log_level="debug")`
  - 第二批（中等价值）：用户操作回调（保存、打开、删除）改为 `@safe_call(show_error="操作失败")`
  - 第三批（低优先级）：纯内部调用可保持原样
- **难度**：中（2-3 小时分批替换）

### 4.6 v2 新增的 P1 问题

#### `BUG-018` [P1] _(v2新增)_ `editor_settings_dialog` 键名前缀冲突

- **位置**：`src/editor/editor_settings_dialog.py:182-196`
- **现象**：`get_settings()` 返回字典中混用了 `editor.*` 命名空间和 `secretary.*` 命名空间的键：

```python
return {
    "show_line_numbers": ...,
    ...
    "show_secretary": self.show_secretary_cb.isChecked(),     # 实际是 secretary.show_secretary
    "secretary_size_percent": self.secretary_size_slider.value(),  # 实际是 secretary.size_percent
}
```

调用方 `main_window._show_editor_settings:680-682` 显式分流，逻辑正确，但**未来扩展时容易出错**——如果新增一个秘书设置，开发者很可能直接加到字典里却忘记在 main_window 处理分流。

- **修复方案**：让 `get_settings()` 返回带命名空间的嵌套字典：

```python
return {
    "editor": {
        "show_line_numbers": ...,
        ...
    },
    "secretary": {
        "show_secretary": ...,
        "size_percent": self.secretary_size_slider.value(),
    },
}
```

调用方根据命名空间分流。

- **难度**：低（30 分钟）

#### `BUG-019` [P1] _(v2新增)_ MarkdownHighlighter 多级标题字体大小相同

- **位置**：`src/editor/syntax_highlighter.py:82-101`
- **现象**：

```python
h1_fmt = QTextCharFormat()
h1_fmt.setForeground(QColor("#000000"))
h1_fmt.setFontWeight(QFont.Bold)
self.h1_format = h1_fmt

h2_fmt = QTextCharFormat()
h2_fmt.setForeground(QColor("#000000"))
h2_fmt.setFontWeight(QFont.Bold)
self.h2_format = h2_fmt

h3_fmt = QTextCharFormat()
h3_fmt.setForeground(QColor("#000000"))
h3_fmt.setFontWeight(QFont.Bold)
self.h3_format = h3_fmt
```

H1、H2、H3 三个级别**只有黑色加粗、无字号差异**，对仿 PyCharm/JetBrains 风格而言不够直观。

- **修复方案**：分级设字号：

```python
h1_fmt.setFontPointSize(base_size * 1.4)  # H1 大 40%
h2_fmt.setFontPointSize(base_size * 1.25) # H2 大 25%
h3_fmt.setFontPointSize(base_size * 1.15) # H3 大 15%
h456_fmt.setFontPointSize(base_size * 1.05)
```

- **难度**：低（20 分钟）

#### `QUAL-020` [P1] _(v2新增)_ `minimap` 块缓存失效粒度过粗

- **位置**：`src/editor/minimap.py:61-66`、`70-72`
- **现象**：

```python
def _invalidate_and_repaint(self):
    self._cache_valid = False
    if self._use_block_cache:
        self._block_cache.clear()    # ← 任何变化清空所有块缓存
        self._block_dirty.clear()
    self.update()

def resizeEvent(self, event):
    super().resizeEvent(event)
    self._cache_valid = False
    if self._use_block_cache:
        self._block_cache.clear()    # ← resize 也清空所有块
```

`_block_dirty` 字段定义了但**从未被添加元素**——只有 `discard` 调用，没有 `add`。所谓"块级失效"的设计实际上是"全部失效"。

- **影响**：feature flag `minimap_block_cache` 即使开启，性能改进非常有限——任何打字、滚动条调整、resize 都会清空所有块缓存，与全文重绘无差。
- **修复方案**：实现真正的块级失效：监听 `QTextDocument.blocksChanged(int from_block, int char_added, int char_removed)`，把受影响的 BLOCK_SIZE 块加入 `_block_dirty`。或者简化掉块缓存机制，改名实事求是。
- **难度**：高（真正实现 1 天）/ 低（简化 30 分钟）

---

## 5. P2 — 架构与代码质量改进

### 5.1 架构性死代码与"虚假繁荣"

#### `ARCH-003` [P2] 存储抽象层（`src/storage/`）完全未被业务代码调用

- **位置**：`src/storage/`（685 行 + 5 文件 + 测试）
- **现象**：用 grep 全局搜索 `StorageFactory|JsonStorage|SqliteStorage` 在 `src/` 内（除 `src/storage/` 自身外）**零调用方**。`config.py` 仍然直接 `_load_json` / `_save_json` 读写 JSON。
- **影响**：阶段五"数据存储抽象层"是空架子；663+22 行实现 + 27 个测试用例占用维护成本却无业务价值。
- **修复方案**（二选一）：
  - **方案 A（推荐）**：删除 `src/storage/` 与对应测试，从文档中移除该章节
  - **方案 B**：让 `Config` 通过 `StorageFactory.create_from_config()` 获取实例，把 `_load_json`/`_save_json` 替换为接口调用
- **难度**：低（方案 A 半天）/ 高（方案 B 1-2 天）

#### `ARCH-004` [P2] 主题系统覆盖范围有限（29 处独立 setStyleSheet）

- **位置**：`src/themes/theme_engine.py` + 12 个独立组件
- **现象**：`MainWindow._apply_theme()` 只对 `self.setStyleSheet(stylesheet)`，但项目中**29 处独立 `setStyleSheet`** 调用在子组件中。
- **影响**：用户切换"深色主题"时，菜单栏会变暗，但**编辑器、文件树、状态栏、立绘、资源栏全部仍是浅色**。
- **修复方案**：组件订阅主题变化信号，主动更新自身样式（详细设计见 v1 报告）。
- **难度**：高（3-5 天）

#### `ARCH-005` [P2] `Config` 类职责过重（639 行）

- **位置**：`src/core/config.py`
- **现象**：单类同时管理 settings/workspace/savegame 三文件、路径验证、文件安全、输入验证、加密管理。
- **修复方案**：拆出 `SavegameManager` 和 `SecurityManager`。
- **难度**：高（1-2 天）

#### `ARCH-006` [P2] `EventBus` 仅做信号中转

- **位置**：`src/core/event_bus.py`
- **现象**：`connect_signals` 把信号连接集中起来，但所有 `handle_xxx` 方法都把 MainWindow 作为参数再调回 mw 上的方法。**不是真正的发布-订阅**。
- **修复方案**：
  - **方案 A**：实现真正的发布-订阅，组件间不再相互直接引用
  - **方案 B**：移除 EventBus，把信号连接分散回 MainWindow（更简洁）
- **难度**：中（方案 B 半天）/ 高（方案 A 2-3 天）

#### `ARCH-007` [P2] 插件 PluginAPI 仅提供只读接口

- **位置**：`src/plugins/plugin_sandbox.py:46-80`
- **现象**：`PluginAPI` 全部是 `get_*` 方法，插件无法向主程序写入任何数据或触发操作。
- **修复方案**：扩展 PluginAPI，新增 `open_file`、`show_message`、`register_command`、`get_config` 等接口（含权限检查）。
- **难度**：中（1 天）

#### `ARCH-008` [P2] _(v2新增)_ dpi_helper 在生产环境是 no-op

- **位置**：`src/utils/dpi_helper.py:40-50`、`main.py:33`
- **现象**：

```python
# main.py 第 33 行
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)

# dpi_helper.py 第 46-49 行
if app.testAttribute(Qt.AA_EnableHighDpiScaling):
    _scale_factor = 1.0
    _initialized = True
    return        # ← 直接返回，scale_factor 永远是 1.0
```

随后所有 `scale(value)` 调用都返回 `value` 本身，`scale_stylesheet` 也不做任何替换。`shortcut_panel.py` 中 6 处 `scale(...)` 调用、`secretary_widget.py` 中的 `scale_size`、main_window 中的所有 dpi_helper 引用**都是 no-op**。

- **影响**：
  - 161 行 dpi_helper 代码 + `tests/test_dpi_helper.py` 完全无业务价值
  - 文档第 11 条"所有 UI 尺寸通过 `dpi_helper.scale()` 计算"是虚假承诺
  - 但**Qt 的 AA_EnableHighDpiScaling 已经能处理大部分情况**，所以视觉效果上 **没有问题**——只是代码组织上是冗余的
- **修复方案**（二选一）：
  - **方案 A（推荐，工作量小）**：保留 dpi_helper 作为"便利封装"——比如 `scale()` 仍然有用（语义上表达"这是个像素值"），但删除 `init_dpi` 和 `_scale_factor` 计算逻辑，文档诚实化为"在 AA_EnableHighDpiScaling 启用情况下，scale() 返回原值，仅供语义标注"
  - **方案 B**：禁用 `AA_EnableHighDpiScaling`，自己处理 DPI（不推荐，工作量大且容易出错）
- **难度**：低（方案 A）

#### `ARCH-009` [P2] _(v2新增)_ LazyLoader 类整体是空架子

- **位置**：`src/utils/lazy_loader.py:19-65`
- **现象**：`LazyLoader.register / get / add_deferred_init / run_deferred_inits` 共 65 行，全项目零调用方。仅 `StartupProfiler` 有用（被 main_window 和 main.py 调用）。
- **影响**：`tests/test_lazy_loader.py` 类似于装饰品。
- **修复方案**：要么删除 `LazyLoader` 类（保留 `StartupProfiler`），要么真正接入——把 GameEngine、ThemeEngine、PluginManager 等非核心模块改为延迟创建。
- **难度**：低（删除）/ 中（接入）

#### `ARCH-010` [P2] _(v2新增)_ MenuBuilder 与 ShortcutManager 各管一套快捷键

- **位置**：`src/core/menu_builder.py` + `src/core/shortcut_manager.py`
- **现象**：见 §2.4。MenuBuilder 直接 `action.setShortcut(QKeySequence("Ctrl+S"))`，与 ShortcutManager 的 `_DEFAULT_SHORTCUTS` 中的 `file.save = "Ctrl+S"` 平行存在但不联动。
- **影响**：参见 `BUG-013`——用户的自定义快捷键不影响菜单项 QAction。
- **修复方案**：与 `BUG-013` 合并修复——MenuBuilder 接受 ShortcutManager 实例，所有菜单项通过 `manager.get_action(action_id)` 获取 QAction。
- **难度**：高（1-2 天，与 BUG-013 合并）

#### `BUG-012` [P2] `file_guard` 超时机制无法真正中断

- **位置**：`src/security/file_guard.py:178-197`
- **现象**：`thread.join(timeout)` 后若 `is_alive` 抛 TimeoutError，但 daemon 线程会继续运行直到自然结束。
- **修复方案**：分块读取 + 检查 `should_stop` 标志；或文档诚实化（"超时控制" 改为"等待超时上限"）。
- **难度**：中（2 小时）/ 低（30 分钟仅文档）

### 5.2 IO 与并发问题

#### `QUAL-008` [P2] `auto_pair_handler.py` 6 处 silent except

- **位置**：`src/editor/auto_pair_handler.py:153, 184, 195, 223, 249, 260`
- **现象**：处理 IME 行为差异，但 `except Exception: pass` 完全静默。
- **修复方案**：替换为 `@safe_call(log_level="debug")` 装饰器；或改为 `except Exception as e: logger.debug(...)`。
- **难度**：低（30 分钟）

### 5.3 样式与主题

#### `QUAL-009` [P2] `FindReplaceBar` 样式硬编码

- **位置**：`src/editor/find_replace.py:54, 376, 379, 383`
- **修复方案**：随 `ARCH-004` 整体处理。

#### `QUAL-010` [P2] 标签页样式硬编码

- **位置**：`src/editor/editor_tabs.py:205`
- **修复方案**：随 `ARCH-004` 整体处理。

#### `QUAL-021` [P2] _(v2新增)_ `theme_engine.generate_stylesheet` 全局 QLabel/QPushButton 样式与组件局部样式冲突

- **位置**：`src/themes/theme_engine.py:330-356`
- **现象**：theme_engine 生成的 QSS 包含全局 `QLabel { color: ... }` 等通用规则，但很多组件自己设了 `setStyleSheet("color: #999;")` 等。Qt CSS 的优先级规则决定**组件局部样式覆盖主窗口样式**——切换主题后，没设独立样式的 QLabel 会变色，设了局部样式的不变，**导致视觉不一致**。
- **修复方案**：与 `ARCH-004` 合并处理。组件局部样式应改为从主题读取颜色，或使用更精细的 CSS 选择器（如 `#hint_label`）让主题可以覆盖。
- **难度**：高（随 ARCH-004）

### 5.4 其他

#### `QUAL-011` [P2] `path_validator` 与 `input_validator` 都实现了 `validate_filename`

- **位置**：`src/security/path_validator.py:157` 与 `src/security/input_validator.py:70`
- **修复方案**：保留 `input_validator` 版本，从 path_validator 删除并改为调用 input_validator。
- **难度**：低（30 分钟）

#### `QUAL-012` [P2] `incremental_renderer` 每次按键对整个文件做 MD5

- **位置**：`src/editor/incremental_renderer.py:78`
- **修复方案**：在 `_last_text == text` 早返回之后再计算 hash。
- **难度**：低（合并到 ARCH-002）

#### `INFRA-002` [P2] 导入风格混用（绝对 vs 相对）

- **位置**：全项目
- **现象**：`config.py`、`security/*.py` 用绝对导入；`main_window.py`、`editor/*.py`、`game/*.py` 用相对导入。
- **修复方案**：全部改为相对导入。
- **难度**：低（1 小时）

#### `QUAL-022` [P2] _(v2新增)_ `StartupProfiler` 调用方有重复阶段名

- **位置**：`src/main_window.py:53-90`、`main.py:49-79`
- **现象**：MainWindow 和 main.py 各自调用 `profiler.begin_phase(...)` / `end_phase()`，但有重复的阶段名（如"配置初始化"、"日志初始化"在 main.py，"游戏引擎初始化"、"UI初始化"在 MainWindow）。整个启动流程的耗时被分散在两个文件，难以关联。
- **修复方案**：统一在 main.py 中管理阶段，MainWindow 把自己的初始化耗时通过回调或属性暴露给 profiler。或简化为单一总耗时记录（详细分阶段是过度设计）。
- **难度**：低（半小时）

---

## 6. P3 — 工程化与配置

| ID                    | 标题                                                | 位置                                                                                        | 现象/修复                                                                                                                                                                              |
| --------------------- | --------------------------------------------------- | ------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `INFRA-003`           | 行尾符不统一                                        | 4 文件 CRLF（editor.py、menu_builder.py、event_bus.py、plugin_manager.py），其余 46 文件 LF | 添加 `.gitattributes` 写 `* text=auto eol=lf`                                                                                                                                          |
| `INFRA-004`           | 缺 `.gitignore`                                     | 仓库根                                                                                      | 仓库内含 `__pycache__/`、`temp/autosave/`、`benchmarks/results/`、`data/config/`、`data/gamedata/` 等不该提交的产物                                                                    |
| `INFRA-005`           | `notebooks/` 含用户数据                             | 仓库根                                                                                      | `notebooks/1.txt` 是用户数据，不应提交。通过 `.gitignore` 排除                                                                                                                         |
| `INFRA-006`           | `benchmarks/` 在根目录                              | 仓库根                                                                                      | 该目录的 `__init__.py` 让其成为可导入包，可能干扰打包；建议移至 `tests/benchmarks/`                                                                                                    |
| `QUAL-013`            | `bauxite_counter` 即时持久化时机                    | `game_engine.py:51`                                                                         | 与 `BUG-008` 合并修复                                                                                                                                                                  |
| `QUAL-014`            | `secretary_widget` 立绘缩放硬编码 fallback          | `secretary_widget.py:333-336`                                                               | `max_h = 200 / max_w = 150` 未走 `dpi_helper`（虽然 `ARCH-008` 指出 dpi_helper 实际是 no-op，但语义上仍应保持一致）                                                                    |
| `QUAL-015`            | `QInputDialog` 导入位置远离使用点                   | `editor/editor_tabs.py`                                                                     | 文件顶部导入但使用在第 1090 行附近。功能上无问题                                                                                                                                       |
| `QUAL-023` _(v2新增)_ | `feature_flags._save` silent except                 | `src/utils/feature_flags.py:95-96`                                                          | `try: ... except Exception: pass`——磁盘写失败时用户感知不到，feature flag 修改不会持久化。改为 `except Exception as e: get_logger(__name__).warning("保存 feature flags 失败: %s", e)` |
| `QUAL-024` _(v2新增)_ | `feature_flags.init_flags` silent except            | 第 38-39 行                                                                                 | 同上                                                                                                                                                                                   |
| `QUAL-025` _(v2新增)_ | `lazy_loader._show_error_dialog` silent except 嵌套 | `exceptions.py:101-102`                                                                     | `try: from .error_handler import ...` 失败时静默 pass。这是延迟导入处理循环依赖的合理做法，但应至少 `print` 而非完全静默                                                               |
| `QUAL-026` _(v2新增)_ | `MarkdownHighlighter` 标题字号同                    | `syntax_highlighter.py:82-101`                                                              | 与 `BUG-019` 合并                                                                                                                                                                      |

---

## 7. 未完成功能模块清单

> 这些是规划中、当前未实现的功能。与 `BUG-004`（空函数）的区别在于：那些是有菜单入口但无实现，这里是整个模块都未开始。

### 7.1 核心玩法链路

#### `TODO-001` [P0] 打字奖励系统（参见 P0 章节）

#### `TODO-003` [P1] 建造系统

- **现状**：
  - `data/gamedata/characters.json` 已定义 10 个角色，含 `threshold`、`build_time_minutes`、`rarity` 等
  - `savegame.json` 有 `construction_queue` 字段
  - `game_sidebar.py` 已有"建造"按钮但点击后是空白容器
- **需实现**：资源投入界面、2 槽位建造队列、阈值过滤、概率抽取、加速消耗核心
- **难度**：高（3-5 天）

#### `TODO-004` [P1] 图鉴系统

- **现状**：`savegame.json` 有 `owned_characters`、`achievements`，无 UI 与逻辑
- **需实现**：角色卡片展示、立绘查看、语音播放、重复获得转核心、成就系统
- **难度**：高（3-5 天）

#### `TODO-005` [P1] 车库系统

- **现状**：仅有侧边栏"库"按钮，视图为空白
- **需实现**：角色详情界面，展示已获得角色立绘、属性、获得记录、皮肤切换
- **难度**：高（2-3 天）

### 7.2 配套界面

#### `TODO-006` [P1] 游戏设置对话框

- **现状**：`_show_game_settings()` 是空函数（也是 `BUG-004` 的一部分）
- **需实现**：挂机奖励倍率、每日打字上限、建造槽位扩容、加密设置等
- **难度**：中（1 天）

#### `TODO-007` [P2] 导入角色数据 / 导入外部文档

- **现状**：菜单项存在，函数体为 `pass`
- **难度**：中

#### `TODO-008` [P2] 新手攻略 / 使用说明

- **现状**：菜单项存在，函数体为 `pass`
- **需实现**：内置帮助文档查看器，可基于 `MarkdownPreviewWidget` 渲染随附的指南 .md
- **难度**：低（半天）

---

## 8. 可增加的小型功能建议

按"用户价值 / 实现难度"性价比排序。每项均与现有架构兼容、改动量小。

> **v1 → v2 修正**：v1 报告中的 `FEAT-015 快捷键速查面板入口` 已删除——验证确认 ShortcutPanel 已绑定 Ctrl+/，详见 `src/main_window.py:596-603` 与 `src/core/menu_builder.py:170`。

### 8.1 高价值 + 低难度（强烈推荐）

#### `FEAT-001` 拖放文件到窗口打开

- **实现**：重写 `MainWindow.dragEnterEvent` / `dropEvent`，解析 `urls()` 调用 `_open_file`
- **难度**：低（1-2 小时）
- **价值**：高（现代编辑器标配）

#### `FEAT-002` 标签页中键关闭

- **实现**：`DraggableTabBar.mousePressEvent` 检测 `Qt.MiddleButton`
- **难度**：低（30 分钟）
- **价值**：中-高

#### `FEAT-003` 最近关闭文件列表（Reopen Closed Tab）

- **实现**：`_close_tab` 时把 `(filepath, cursor_position)` 推入栈；`Ctrl+Shift+T` 弹出栈顶文件
- **难度**：低（1 小时）
- **价值**：高（防误关）

#### `FEAT-004` 字符/词数/行数实时统计

- **实现**：扩展 `StatusBarWidget`，监听 `cursorPositionChanged` 与 `textChanged`（合并到 `PERF-002` 的信号驱动改造）
- **难度**：低（1 小时）
- **价值**：高 — **同时是打字奖励系统（`TODO-001`）的前置基础设施**

#### `FEAT-005` 最近文件菜单

- **现状**：`config.py` 已有 `add_recent_file` / `get_recent_files`，菜单已通过 `mw.recent_menu = menu.addMenu("最近打开")` 创建
- **实现**：核对 `_update_recent_menu()` 是否真的填充了菜单项（v1 报告未确认；如果已实现则此项删除）
- **难度**：低（半小时核实/补全）
- **价值**：高

### 8.2 中价值 + 低难度

#### `FEAT-006` 文件类型图标

- **实现**：`QFileIconProvider` 或自定义图标映射，应用到标签页和文件树
- **难度**：低
- **价值**：中（视觉识别）

#### `FEAT-007` 会话恢复光标位置

- **实现**：`_tab_info` 增加 `cursor_position` 字段，关闭/启动时序列化到 `workspace.json`
- **难度**：低（1 小时）
- **价值**：中-高

#### `FEAT-008` 自动配对状态显示

- **实现**：状态栏读取 `config` 中的 `auto_pair_brackets` 设置
- **难度**：低
- **价值**：低（辅助信息）

#### `FEAT-009` 小秘书互动增强

- **实现**：双击立绘切换角色；闲置 5 分钟以上自动随机台词
- **难度**：低
- **价值**：中（趣味性）

### 8.3 高价值 + 中难度

#### `FEAT-010` 编辑器分屏（Split Editor）

- **实现**：基于 `QSplitter`，把 `editor_container` 嵌入分屏容器
- **难度**：中（1-2 天）
- **价值**：高（对比编辑）

#### `FEAT-011` 书签

- **实现**：`Ctrl+F2` 在当前行打书签，`F2`/`Shift+F2` 跳转
- **难度**：中（1 天）
- **价值**：中-高

#### `FEAT-012` 导出 PDF / HTML（Markdown）

- **实现**：`QWebEngineView` 自带 `printToPdf()`
- **难度**：低（1 小时）
- **价值**：中-高

### 8.4 工程化层

#### `FEAT-013` 崩溃日志自动收集

- **实现**：`main.py` 注册 `sys.excepthook`，未捕获异常写到 `logs/crash_<时间>.log`，下次启动时检测并提示
- **难度**：低（半天）
- **价值**：中

#### `FEAT-014` 设置导入/导出

- **实现**：菜单加"导出设置"和"导入设置"
- **难度**：低（1 小时）
- **价值**：中

### 8.5 游戏化层

#### `FEAT-016` 每日签到

- **实现**：每天首次启动给固定资源
- **难度**：低
- **价值**：中

#### `FEAT-017` 资源仓库容量上限

- **实现**：当前在线挂机无上限，资源会无限累积。设上限（如 fuel ≤ 99999）
- **难度**：低
- **价值**：中（为建造系统铺路）

### 8.6 v2 新增建议

#### `FEAT-018` _(v2新增)_ 多级标题字号差异化

- **现状**：见 `BUG-019`
- **实现**：H1/H2/H3/H456 分别 1.4x/1.25x/1.15x/1.05x 基础字号
- **难度**：低（20 分钟，与 BUG-019 合并）
- **价值**：中（视觉层次）

#### `FEAT-019` _(v2新增)_ 从文件树双击外部文件添加到外部文件区

- **现状**：file_tree.py 已支持显示外部文件，但**新增外部文件的入口**未在文件树菜单中提供
- **实现**：在右键菜单"新建文件"附近加"添加外部文件...
- **难度**：低（30 分钟）
- **价值**：中

#### `FEAT-020` _(v2新增)_ 编辑器格式化支持更多文件类型

- **现状**：`format_document` 只支持 JSON / XML / HTML
- **实现**：添加 YAML（用 `pyyaml`）、TOML（用 `tomli_w`）、CSS（用 `cssbeautifier`）
- **难度**：中（1 天，含依赖添加）
- **价值**：中

#### `FEAT-021` _(v2新增)_ minimap 双击跳转 + Ctrl+点击预览

- **现状**：minimap 仅支持单击/拖拽滚动
- **实现**：双击跳转到该位置（光标真正落到该行）；Ctrl+点击仅预览（鼠标移开恢复原位置）
- **难度**：低（1 小时）
| ID | 类别 | 标题 | 修复难度 |
|---|---|---|---|
| `INFRA-001` | 构建 | `pyproject.toml` 的 build-backend 字符串无效 | 低 |
| `BUG-001` | 功能缺陷 | `_reset_settings()` 函数体为空 | 中 |
| `BUG-002` | 功能缺陷 | `open_file` 编码检测缩进错误 | 低 |
| `BUG-003` | 功能缺陷 | 搜索框拒绝合法输入（XSS 检测错位） | 低 |
| `BUG-004` | 功能缺陷 | 9 个菜单项是空函数 | 低 |
| `BUG-005` | 功能缺陷 | 版本号硬编码三处 | 低 |
| ⭐ `BUG-013` | 架构/功能 | ShortcutManager 实例化后从未注册 | 高 |
| ⭐ `BUG-014` | 配置 | 快捷键启动时 9 条系统冲突警告 | 低 |
| `SEC-001` | 安全 | Markdown 预览启用了原始 HTML | 低 |
| `SEC-002` | 安全 | 本地图片路径解析未走 PathValidator | 低 |
| `SEC-003` | 安全 | 加密存档可能被默认数据覆写 | 中 |
| `TODO-001` | 未完成 | 打字奖励核心逻辑未接入 textChanged | 中 |
| `BUG-001`    | 功能缺陷  | `_reset_settings()` 函数体为空               | 中       | ✅ 已修复 |
| `BUG-002`    | 功能缺陷  | `open_file` 编码检测缩进错误                 | 低       | ✅ 已修复 |
| `BUG-003`    | 功能缺陷  | 搜索框拒绝合法输入（XSS 检测错位）           | 低       | ✅ 已修复 |
| `BUG-004`    | 功能缺陷  | 9 个菜单项是空函数                           | 低       | ✅ 已修复 |
| `BUG-005`    | 功能缺陷  | 版本号硬编码三处                             | 低       | ✅ 已修复 |
| ⭐ `BUG-013` | 架构/功能 | ShortcutManager 实例化后从未注册             | 高       | ✅ 已修复 |
| ⭐ `BUG-014` | 配置      | 快捷键启动时 9 条系统冲突警告                | 低       | ✅ 已修复 |
| `SEC-001`    | 安全      | Markdown 预览启用了原始 HTML                 | 低       | ✅ 已修复 |
| `SEC-002`    | 安全      | 本地图片路径解析未走 PathValidator           | 低       | ✅ 已修复 |
| `SEC-003`    | 安全      | 加密存档可能被默认数据覆写                   | 中       | ✅ 已修复 |
| `TODO-001`   | 未完成    | 打字奖励核心逻辑未接入 textChanged           | 中       | ✅ 已修复 |

### 9.2 P1 — 一般问题

| ID                    | 类别     | 标题                                                  | 修复难度 |
| --------------------- | -------- | ----------------------------------------------------- | -------- |
| `SEC-004`             | 安全     | 插件沙箱不是真正的沙箱（文档诚实化）                  | 低/高    |
| `SEC-005`             | 安全     | `path_validator` 含死代码与重复正则                   | 低       |
| `SEC-006`             | 安全     | `MAX_PATH_LENGTH = 260` 过严                          | 低       |
| `SEC-007`             | 安全     | 多处 QMessageBox 绕过 ErrorHandler                    | 中       |
| `PERF-001`            | 性能     | `_on_text_changed` 大文件性能差                       | 中       |
| ⭐ `PERF-002`         | 性能     | `stats_timer` 500ms 高频轮询                          | 中       |
| `BUG-006`             | 功能缺陷 | `save_all` 中 `save_current_as` 切换标签闪烁          | 中       |
| `BUG-007`             | 功能缺陷 | `_save_user_data_path` 用裸 `open()` 而非 FileGuard   | 低       |
| `BUG-008`             | 设计     | `bauxite_counter` 存放在 settings 而非 savegame       | 低       |
| `BUG-009`             | 类型     | `async_highlight` 返回值类型不一致                    | 中       |
| `BUG-010`             | 配置     | `config.py` `max_file_size = 10MB` 与文档 50MB 不一致 | 低       |
| `BUG-011`             | 日志     | `is_path_in_whitelist` 警告日志刷屏                   | 低       |
| ⭐ `BUG-016`          | 数据安全 | file_tree 删除文件不进回收站                          | 低       |
| ⭐ `BUG-017`          | 功能缺陷 | plugin_manager 热重载失效                             | 低       |
| ⭐ `BUG-018`          | 设计     | `editor_settings_dialog` 键名前缀冲突                 | 低       |
| ⭐ `BUG-019`          | 视觉     | MarkdownHighlighter 多级标题字号相同                  | 低       |
| `ARCH-001`            | 架构     | `VirtualScrollManager` 名不副实                       | 低/高    |
| `ARCH-002`            | 架构     | `IncrementalRenderer` 名不副实                        | 低       |
| `QUAL-001`            | 质量     | `async_highlight` LRU 实现是 FIFO                     | 低       |
| `QUAL-002`            | 质量     | `config.py` 5 个 `get_*_setting` 方法重复             | 低       |
| `QUAL-003`            | 质量     | `main_window.py` 仍过长（927 行）                     | 中       |
| `QUAL-004`            | 质量     | 插件管理对话框关闭重开模式                            | 低       |
| `QUAL-005`            | 质量     | `_show_plugin_manager` 重复导入 PyQt5 组件            | 低       |
| `QUAL-006`            | 质量     | `_get_editor_from_widget` 在批量操作中反复调用        | 低       |
| `QUAL-007`            | 质量     | `CryptoManager` 使用 `..` 相对路径                    | 低       |
| ⭐ `QUAL-016`         | 质量     | ErrorHandler 敏感信息正则会误伤                       | 低       |
| ⭐ `QUAL-017`         | 质量     | JSON 格式化忽略缩进设置                               | 低       |
| ⭐ `QUAL-018`         | 质量     | `format_document` 不支持的文件类型静默无反馈          | 低       |
| ⭐ `QUAL-019`         | 质量     | `safe_call` 装饰器使用率极低                          | 中       |
| ⭐ `QUAL-020`         | 质量     | `minimap` 块缓存失效粒度过粗                          | 低/高    |
| `DOC-001` ~ `DOC-015` | 文档     | 多项文档与代码不一致（含 v2 新增 5 项）               | 低       |

### 9.3 P2 — 架构与代码质量改进

| ID            | 类别   | 标题                                                               | 修复难度               |
| ------------- | ------ | ------------------------------------------------------------------ | ---------------------- |
| `ARCH-003`    | 架构   | 存储抽象层完全无业务调用方                                         | 低（删除）/ 高（接入） |
| `ARCH-004`    | 架构   | 主题系统覆盖范围有限（29 处独立 setStyleSheet）                    | 高                     |
| `ARCH-005`    | 架构   | `Config` 类职责过重（639 行）                                      | 高                     |
| `ARCH-006`    | 架构   | `EventBus` 仅做信号中转                                            | 中/高                  |
| `ARCH-007`    | 架构   | PluginAPI 仅提供只读接口                                           | 中                     |
| ⭐ `ARCH-008` | 架构   | dpi_helper 在生产环境是 no-op                                      | 低                     |
| ⭐ `ARCH-009` | 架构   | LazyLoader 类整体是空架子                                          | 低                     |
| ⭐ `ARCH-010` | 架构   | MenuBuilder 与 ShortcutManager 各管一套快捷键                      | 高                     |
| `BUG-012`     | 并发   | `file_guard` 超时无法真正中断                                      | 低/中                  |
| `QUAL-008`    | 质量   | `auto_pair_handler.py` 6 处 silent except                          | 低                     |
| `QUAL-009`    | 样式   | `FindReplaceBar` 样式硬编码                                        | 低（随 ARCH-004）      |
| `QUAL-010`    | 样式   | 标签页样式硬编码                                                   | 低（随 ARCH-004）      |
| `QUAL-011`    | 质量   | `path_validator` 与 `input_validator` 重复实现 `validate_filename` | 低                     |
| `QUAL-012`    | 性能   | `incremental_renderer` 每次按键 MD5 整文件                         | 低                     |
| ⭐ `QUAL-021` | 样式   | theme_engine 全局样式与组件局部样式冲突                            | 高（随 ARCH-004）      |
| ⭐ `QUAL-022` | 质量   | `StartupProfiler` 调用方分散导致难以关联                           | 低                     |
| `INFRA-002`   | 工程化 | 导入风格混用                                                       | 低                     |

### 9.4 P3 — 工程化与配置

| ID            | 类别   | 标题                                                | 修复难度         |
| ------------- | ------ | --------------------------------------------------- | ---------------- |
| `INFRA-003`   | 工程化 | 行尾符不统一                                        | 低               |
| `INFRA-004`   | 工程化 | 缺 `.gitignore`                                     | 低               |
| `INFRA-005`   | 工程化 | `notebooks/` 含用户数据未排除                       | 低               |
| `INFRA-006`   | 工程化 | `benchmarks/` 在根目录                              | 低               |
| `QUAL-013`    | 质量   | `bauxite_counter` 即时持久化时机                    | 低（随 BUG-008） |
| `QUAL-014`    | 质量   | `secretary_widget` 立绘缩放硬编码 fallback          | 低               |
| `QUAL-015`    | 质量   | `QInputDialog` 导入位置远离使用点                   | 低               |
| ⭐ `QUAL-023` | 质量   | `feature_flags._save` silent except                 | 低               |
| ⭐ `QUAL-024` | 质量   | `feature_flags.init_flags` silent except            | 低               |
| ⭐ `QUAL-025` | 质量   | `lazy_loader._show_error_dialog` silent except 嵌套 | 低               |

### 9.5 未完成功能

| ID         | 优先级 | 标题                 | 难度 |
| ---------- | ------ | -------------------- | ---- |
| `TODO-001` | P0     | 打字奖励核心逻辑接入 | 中   |
| `TODO-003` | P1     | 建造系统             | 高   |
| `TODO-004` | P1     | 图鉴系统             | 高   |
| `TODO-005` | P1     | 车库系统             | 高   |
| `TODO-006` | P1     | 游戏设置对话框       | 中   |
| `TODO-007` | P2     | 导入角色 / 文档      | 中   |
| `TODO-008` | P2     | 新手攻略 / 使用说明  | 低   |

### 9.6 新功能建议

| ID            | 价值  | 难度 | 标题                              |
| ------------- | ----- | ---- | --------------------------------- |
| `FEAT-001`    | 高    | 低   | 拖放文件到窗口打开                |
| `FEAT-002`    | 中-高 | 低   | 标签页中键关闭                    |
| `FEAT-003`    | 高    | 低   | 最近关闭文件列表                  |
| `FEAT-004`    | 高    | 低   | 字符/词数实时统计（打字奖励前置） |
| `FEAT-005`    | 高    | 低   | 最近文件菜单                      |
| `FEAT-006`    | 中    | 低   | 文件类型图标                      |
| `FEAT-007`    | 中-高 | 低   | 会话恢复光标位置                  |
| `FEAT-008`    | 低    | 低   | 自动配对状态显示                  |
| `FEAT-009`    | 中    | 低   | 小秘书互动增强                    |
| `FEAT-010`    | 高    | 中   | 编辑器分屏                        |
| `FEAT-011`    | 中-高 | 中   | 书签                              |
| `FEAT-012`    | 中-高 | 低   | 导出 PDF / HTML                   |
| `FEAT-013`    | 中    | 低   | 崩溃日志自动收集                  |
| `FEAT-014`    | 中    | 低   | 设置导入/导出                     |
| `FEAT-016`    | 中    | 低   | 每日签到                          |
| `FEAT-017`    | 中    | 低   | 资源仓库容量上限                  |
| ⭐ `FEAT-018` | 中    | 低   | 多级标题字号差异化                |
| ⭐ `FEAT-019` | 中    | 低   | 文件树添加外部文件入口            |
| ⭐ `FEAT-020` | 中    | 中   | 编辑器格式化支持 YAML/TOML/CSS    |
| ⭐ `FEAT-021` | 低-中 | 低   | minimap 双击跳转 + Ctrl+点击预览  |

---

## 10. 实施路线图

按"先稳定根基、再清理结构、最后扩展功能"的顺序组织。每个阶段都有明确的开始和结束标志，可作为 commit 边界。

### 阶段 A：紧急修复（1 天，全部 P0）

> **目标**：把"装得上、不骗用户、不丢数据、不被恶意 .md 攻击、快捷键真正可用"五件事做到。

| 顺序 | 任务                                                            | 时长              |
| ---- | --------------------------------------------------------------- | ----------------- |
| 1    | `INFRA-001` 修 `pyproject.toml` build-backend                   | 5 分钟            |
| 2    | `BUG-002` `open_file` 编码检测缩进                              | 5 分钟            |
| 3    | `BUG-005` 版本号统一引用 `__version__`                          | 15 分钟           |
| 4    | `BUG-014` ⭐ 修正 `_SYSTEM_SHORTCUTS`（移除 Ctrl+C/V/X/A/Z 等） | 10 分钟           |
| 5    | `BUG-003` 删除搜索框危险模式过滤                                | 30 分钟           |
| 6    | `BUG-004` 9 个空函数加"功能开发中"提示                          | 1 小时            |
| 7    | `BUG-001` 实现 `_reset_settings()` 真实重置逻辑                 | 30 分钟           |
| 8    | `SEC-001` Markdown 预览关闭原始 HTML                            | 5 分钟 + 回归测试 |
| 9    | `SEC-002` 本地图片路径走 PathValidator                          | 1 小时            |
| 10   | `SEC-003` 加密存档保护守卫                                      | 1-2 小时          |
| 11   | `BUG-013` ⭐ ShortcutManager 接入（决定方案 A 还是 B）          | 半天-1 天         |
| 12   | `TODO-001` 打字奖励核心逻辑接入                                 | 1-2 小时          |

**阶段验收**：

- `pip install -e .` 可成功
- 9 个原本静默的菜单项点击后有反馈
- 用户在 .md 笔记里搜索 `javascript:` 不再失败
- 含 `<script>` 的恶意 .md 在预览中不会执行
- 启动日志中没有 9 条快捷键冲突警告
- 用户在快捷键面板修改快捷键能真正生效（如选了方案 A）
- 打字时资源栏字符数会增加，达到阈值有资源奖励

### 阶段 B：一般修复（4-6 天，P1）

> **目标**：项目质量经得起审视，文档与代码自洽，热重载等功能真正可用。

#### B.1 文档与一致性（半天）

- `DOC-001` ~ `DOC-015`：统一 Python 版本（3.11+）、文件大小（50MB 或显式说明）、行数与测试数等
- `BUG-010` `config.py` `max_file_size` 与文档对齐
- `INFRA-003` ~ `INFRA-006`：加 `.gitignore`、`.gitattributes`、清理用户数据

#### B.2 数据安全相关（半天）

- ⭐ `BUG-016` file_tree 删除走回收站（添加 `send2trash` 依赖）
- ⭐ `BUG-017` plugin_manager 热重载 module_name 修正

#### B.3 安全加固（1 天）

- `SEC-004` 沙箱重命名 + 文档诚实化
- `SEC-005` `path_validator` 死代码清理
- `SEC-006` `MAX_PATH_LENGTH` 调到 4096
- `SEC-007` 全局 QMessageBox 改用 ErrorHandler

#### B.4 性能与稳定性（1 天）

- `PERF-001` `_on_text_changed` 改用 `isModified()`
- ⭐ `PERF-002` stats_timer 改为信号驱动（同时落地 `FEAT-004`）
- `BUG-006` `save_all` 标签闪烁修复
- `BUG-007` `_save_user_data_path` 改用 FileGuard
- `BUG-008` `bauxite_counter` 迁移到 savegame
- `BUG-009` `async_highlight` 返回值类型一致化

#### B.5 代码质量（1-2 天）

- `QUAL-001` LRU 实现修正
- `QUAL-002` `config.py` get/set 方法去重
- `QUAL-004` 插件对话框内部刷新
- `QUAL-005` 重复导入清理
- `QUAL-006` 批量操作循环优化
- `QUAL-007` CryptoManager 显式 savegame_dir 参数
- ⭐ `QUAL-016` ErrorHandler 敏感信息正则收紧
- ⭐ `QUAL-017` JSON 格式化读取设置项
- ⭐ `QUAL-018` 格式化不支持类型显示提示
- ⭐ `QUAL-019` 分批替换 silent except 为 @safe_call（高优先级 silent except 至少处理掉）
- `INFRA-002` 导入风格统一为相对导入

#### B.6 名实相符化（半天）

- `ARCH-001` `VirtualScrollManager` 文档诚实化或重命名
- `ARCH-002` `IncrementalRenderer` 删除 `_line_cache`，改名 `RenderCache`
- ⭐ `BUG-018` editor_settings_dialog 返回嵌套字典
- ⭐ `BUG-019` MarkdownHighlighter 标题字号差异化
- `BUG-011` 警告日志降级

**阶段验收**：

- `mypy` / `pytest` 全绿
- 文档"已完成"模块声明与代码现实一致
- 关键路径性能通过 benchmarks 验证不劣化
- 文件树删除有回收站保护
- 插件热重载实际生效

### 阶段 C：架构整改（2-3 周，P2）

> **目标**：清理空架子，把架构落到实处或诚实删除。

| 顺序 | 任务                                       | 推荐方案                                     | 时长          |
| ---- | ------------------------------------------ | -------------------------------------------- | ------------- |
| 1    | `ARCH-003` 存储抽象层去留                  | **删除**（短期价值低）                       | 半天          |
| 2    | ⭐ `ARCH-009` LazyLoader 去留              | **删除 LazyLoader 类，保留 StartupProfiler** | 半天          |
| 3    | ⭐ `ARCH-008` dpi_helper 去留              | **保留 + 文档诚实化**（仍有语义标注价值）    | 半天          |
| 4    | `QUAL-003` 抽离 `PluginManagerDialog`      | 独立类                                       | 1 小时        |
| 5    | `QUAL-008` silent except 加 debug 日志     | 替换 6 处                                    | 30 分钟       |
| 6    | `QUAL-011` `validate_filename` 合并        | 保留 input_validator 版本                    | 30 分钟       |
| 7    | `QUAL-012` `incremental_renderer` MD5 优化 | 早返回 + cache key 简化                      | 1 小时        |
| 8    | ⭐ `QUAL-020` minimap 块缓存简化或重命名   | 简化（不实现真增量）                         | 1 小时        |
| 9    | ⭐ `QUAL-022` StartupProfiler 集中管理     | main.py 统一                                 | 半小时        |
| 10   | `BUG-012` `file_guard` 超时机制改进        | 文档诚实化 + 分块读                          | 2 小时        |
| 11   | `ARCH-007` PluginAPI 扩展                  | 增加写入 API + 权限模型                      | 1 天          |
| 12   | `ARCH-006` EventBus 价值评估               | **简化**（移回 MainWindow）或重写发布订阅    | 半天 / 2-3 天 |
| 13   | `ARCH-005` Config 类职责拆分               | 抽出 SavegameManager + SecurityManager       | 1-2 天        |
| 14   | `ARCH-004` + `QUAL-021` 主题系统全局生效   | 各组件订阅 theme_changed                     | 3-5 天        |

**阶段验收**：

- 不再存在"声称完成但无业务调用"的模块
- 主题切换时所有可见 UI 元素同步更新
- 插件系统能写出真正有用的扩展（含示例插件演示新 API）

### 阶段 D：功能完善（按需，P1 未完成）

> **目标**：项目核心玩法链路完整。

#### D.1 打字奖励完整化（1-2 天）

`TODO-001` 已在阶段 A 完成基础接入。本阶段做：

- `FEAT-004` 字符/词数/行数状态栏（已在阶段 B.4 一并落地）
- 防作弊：粘贴/撤销/连续相同字符不计入
- 递减收益算法在 settings 中可调
- 每日上限到达后的提示

#### D.2 游戏设置对话框（1 天）

- `TODO-006`：实现包含挂机倍率、每日打字上限、建造槽位扩容、加密设置等

#### D.3 建造系统（3-5 天）

- `TODO-003`：完整玩法实现
- 同步实现 `FEAT-017`（资源仓库上限）

#### D.4 图鉴 + 车库（5-7 天）

- `TODO-004` 图鉴
- `TODO-005` 车库
- 配合稀有度展示和重复获得转核心机制

### 阶段 E：日常增强（按性价比，P3 + FEAT）

> **目标**：常用快捷功能补齐。建议按以下顺序：

#### E.1 第一批（半天）

- `FEAT-001` 拖放文件到窗口打开
- `FEAT-002` 标签页中键关闭
- ⭐ `FEAT-019` 文件树添加外部文件入口

#### E.2 第二批（1 天）

- `FEAT-003` 最近关闭文件列表
- `FEAT-005` 最近文件菜单（核实是否已实现）
- `FEAT-007` 会话恢复光标位置

#### E.3 第三批（2-3 天）

- `FEAT-010` 编辑器分屏
- `FEAT-011` 书签
- `FEAT-012` 导出 PDF / HTML
- ⭐ `FEAT-020` 编辑器格式化支持更多文件类型

#### E.4 第四批（半天）

- `FEAT-013` 崩溃日志
- `FEAT-014` 设置导入导出
- `FEAT-016` 每日签到
- `FEAT-009` 小秘书互动增强
- ⭐ `FEAT-021` minimap 双击跳转

---

## 11. 附录：审阅方法与边界

### 11.1 审阅过程

#### v1 审阅（首轮，重点文件深读）

1. **解压并核对版本**：通过 `pyproject.toml` 与 README 确认压缩包是 v1.6.4
2. **建立全局地图**：用 `find` + `wc` 统计 51 个 Python 文件、共 10182 行
3. **静态扫描**：用 grep 找 silent except、TODO 标记、setStyleSheet 调用、import 风格
4. **AST 分析**：找所有嵌套函数定义（v1.6.1 修复过的雷点同类）
5. **关键文件深读**：`main_window.py`、`editor.py`、`editor_tabs.py`、`markdown_preview.py`、`config.py` 等 13 个核心文件
6. **逻辑验证**：对可疑发现（如搜索框验证）用独立 Python 脚本验证实际行为
7. **依赖图分析**：用 AST 检查模块间循环依赖（结果：0 个循环依赖）

#### v2 补充审阅（本轮，覆盖剩余模块）

8. **覆盖剩余模块**：`editor_actions.py`、`syntax_highlighter.py`、`highlight_themes.py`、`minimap.py`、`file_tree.py`、`editor_settings_dialog.py`、`theme_preview.py`、`shortcut_panel.py`、`shortcut_manager.py`、`menu_builder.py`、`event_bus.py`、`timer_manager.py`、`dpi_helper.py`、`feature_flags.py`、`lazy_loader.py`、`logger.py`、`exceptions.py`、`error_handler.py`、`storage_*.py`、`plugin_manager.py`、`plugin_sandbox.py`
9. **空架子检测**：对每个新读模块都做"是否被业务代码实际调用"的 grep 验证
10. **实际逻辑验证**：用独立 Python 脚本验证 ErrorHandler 的敏感信息过滤误伤、ShortcutManager 的快捷键冲突警告等

### 11.2 已审阅模块清单（v2 完整版）

✅ **完整审阅**（30 个核心模块）：

- 主入口：`main.py`、`main_window.py`
- 核心：`config.py`、`event_bus.py`、`menu_builder.py`、`shortcut_manager.py`、`timer_manager.py`
- 编辑器：`editor.py`、`editor_tabs.py`、`editor_actions.py`、`markdown_preview.py`、`auto_pair_handler.py`、`virtual_scroll.py`、`async_highlight.py`、`incremental_renderer.py`、`find_replace.py`、`syntax_highlighter.py`、`highlight_themes.py`、`minimap.py`、`file_tree.py`、`editor_settings_dialog.py`
- UI：`shortcut_panel.py`
- 主题：`theme_engine.py`、`theme_preview.py`
- 安全：`path_validator.py`、`file_guard.py`、`input_validator.py`、`crypto_manager.py`
- 插件：`plugin_manager.py`、`plugin_sandbox.py`、`plugin_base.py`
- 游戏：`game_engine.py`、`secretary_widget.py`
- 存储：`storage_factory.py`、`sqlite_storage.py`、`json_storage.py`、`storage_interface.py`
- 工具：`logger.py`、`exceptions.py`、`error_handler.py`、`feature_flags.py`、`lazy_loader.py`、`dpi_helper.py`

✅ **结构审阅**：`tests/`（29 个测试文件）、`benchmarks/`、`plugins/`（含示例插件）

⚠️ **未深度审阅（剩余少量）**：

- `resource_bar.py`（仅看了头部）
- `game_sidebar.py`（仅看了头部）
- `status_bar.py`、`first_run_dialog.py`（v1 即未审阅）
- 各模块的 `__init__.py`（一般为空或简单 import）

未深度审阅的模块在静态扫描层面已纳入，具体行级问题可能未发现。

### 11.3 未能验证的部分

- **运行时行为**：当前环境无法安装 PyQt5，未能实际跑测试套件
- **打包测试**：未能验证 `pyinstaller` 在当前代码下的行为
- **跨平台行为**：所有分析在 Linux 容器内进行，Windows 特有逻辑（如 `\\?\` 长路径前缀）仅做静态推理
- **压缩包与 GitHub `2026.5.3` 分支字节级一致性**：受 GitHub 防爬限制无法逐文件比对，但版本号一致（v1.6.4）可作合理依据

### 11.4 报告 AI 可读性约定

- 每个问题用稳定 ID（如 `BUG-003`）；后续对话中可直接引用 ID 让 Claude 立即定位
- 修复方案尽量给出可直接套用的代码片段
- 优先级体系（P0/P1/P2/P3）与难度（低/中/高）独立标注
- 文档与代码不一致项单列 `DOC-XXX`
- v2 新增项用 ⭐ 标记便于增量阅读

### 11.5 后续协作建议

如需基于本报告推进工作，建议按以下方式与 AI 协作：

1. **单 ID 推进**：直接说"帮我处理 `BUG-013`"，AI 可基于报告中的描述与方案给出具体改动
2. **批量推进**：说"帮我把阶段 A 的所有 P0 处理掉"，AI 可按顺序逐个产出 diff
3. **分支策略建议**：每个阶段开独立分支（`fix/p0-emergency`、`fix/p1-quality`、`refactor/p2-arch`、`feat/p1-todo`、`feat/enhancement`），合并到主分支前跑测试
4. **回归保障**：阶段 A 与 B 的每个改动都建议补单元测试

### 11.6 v1 → v2 主要变化

**新增问题（共 21 项）**：

- 5 项 DOC（DOC-011 到 DOC-015）
- 7 项 BUG（BUG-013 到 BUG-019）
- 1 项 PERF（PERF-002）
- 6 项 QUAL（QUAL-016 到 QUAL-026 中的部分）
- 3 项 ARCH（ARCH-008 到 ARCH-010）
- 4 项 FEAT（FEAT-018 到 FEAT-021）

**修正的 v1 错误**：

- v1 `FEAT-015 快捷键速查面板入口` 被删除（实际已绑定 Ctrl+/）
- v1 `BUG-005 版本号硬编码`描述更准确（plugin_sandbox.py 已正确使用 **version**，仅 main.py 和 main_window.py 仍硬编码）

**结构调整**：

- 新增 §2「v2 新增的关键发现」做 highlight
- §10 实施路线图阶段 A 增加 `BUG-013` 和 `BUG-014` 两项 P0 任务

---

> _本报告整合自 AI-IDE 自动审阅与 Claude 两轮深度审阅，已交叉去重。所有 ID、行号、代码片段均可在 v1.6.4 源码中追溯验证。如发现描述与实际代码有出入，以代码为准，并欢迎反馈以更新报告。_
