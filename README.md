# PanzerNote v1.7.0

一款以《战车少女》为主题的笔记工具。通过书写获取资源，建造收集角色，点亮完整图鉴。

## 规划中功能（TODO）

- **建造系统**：投入资源建造角色
- **图鉴收集**：收集所有战车娘
- **游戏设置界面**：完善游戏相关设置对话框

## 功能特性

### 记事本功能

- **多标签编辑**：同时打开多个文件，支持标签页拖拽排序，**可拖拽标签到文件树移动文件**
- **语法高亮**：基于Pygments，支持Python、C/C++、Java、JavaScript、JSON、HTML、CSS、XML等30+语言，PyCharm风格配色
- **Markdown分屏预览**：打开.md文件自动启用左编辑右预览的分屏模式，实时同步渲染，**支持本地图片引用**（`![](./img.png)` 自动解析）
- **预览代码高亮**：Markdown预览中的代码块自动语法着色，配色与编辑器完全一致
- **代码块一键复制**：预览中代码块左上角📋按钮，点击即复制代码到剪贴板
- **代码缩略图（Minimap）**：编辑器右侧显示整个文件的鸟瞰图，支持点击/拖拽快速导航，**可设置自动开关缩略图**（.txt和.md不显示）
- **增强型查找替换**：
  - **正则表达式搜索**：支持复杂模式匹配和反向引用替换
  - **大小写敏感切换**：灵活控制匹配规则
  - **全词匹配**：精确查找完整单词
  - **匹配计数**：状态栏实时显示「第 N/M 个匹配」
  - **全部高亮**：所有匹配项黄色标记，当前匹配橙色突出
- **括号/引号自动配对**：输入 `(`、`[`、`{`、`"`、`'` 时自动补全右侧字符，光标置于中间；选中文本时自动包裹（可在设置中开关）。**v1.6.6 性能优化**：非配对字符 O(1) 快速过滤，消除全文复制开销
- **行操作快捷键**：
  - `Ctrl+Shift+K`：删除当前行
  - `Alt+↑ / Alt+↓`：上下移动当前行
  - `Ctrl+Shift+D`：复制当前行到下一行
- **大小写转换**：`Ctrl+Shift+U` 切换大小写，右键菜单支持转大写/小写/首字母大写
- **转到行**：`Ctrl+G` 弹出对话框，输入行号快速跳转
- **JSON/XML格式化**：检测到JSON或XML文件时，右键菜单显示「格式化文档」选项，自动美化缩进
- **自动缩进**：回车后自动保持缩进，Python的`:`和C系语言的`{`自动增加缩进
- **行宽模式切换**：「不换行」（水平滚动）和「限制行宽」（在编辑器宽度处换行）
- **多编码支持**：自动检测UTF-8/GBK/UTF-16编码，另存为时可选择编码
- **文件树管理**：左侧文件树，支持新建/删除/重命名文件和文件夹，**接受标签拖拽实现文件移动**
- **自动保存**：定时暂存，最小化时自动保存，防止数据丢失
- **行号显示**、**当前行高亮**（设置中可独立开关，实时生效）
- **自定义字体**：支持从本地字体库选择字体，自定义字体大小，设置后即时应用
- **记事本设置**：统一的设置对话框，可配置行号、高亮、缩略图、字体、字体大小、括号配对、自动保存间隔等

### 游戏系统

- **资源获取**：
  - 在线挂机：燃料/弹药/钢材每分钟+5，铝材每3分钟+5
  - 离线挂机：收益为在线的1/3（向大取整），最多24小时
  - 打字奖励：每输入字符累计计数，递减收益算法（≤1000字符1.0倍率，1000-3000字符0.4倍率，>3000字符0.1倍率），每日上限10,000字符。**v1.6.6 修复**：IME整句输入不再误判为粘贴，粘贴检测阈值提升至50字符
- **建造系统**：投入资源建造角色（规划中）
- **图鉴收集**：收集所有战车娘（规划中）
- **小秘书**：右下角显示角色立绘和台词气泡，点击互动

### 小秘书立绘系统

立绘文件放在 `data/assets/portraits/` 目录下：

```
portraits/
├── secretary.png              ← 默认立绘
├── 原始/
│   ├── 正常/
│   │   └── {编号} {角色名}-正常.png
│   └── 大破/
│       └── {编号} {角色名}-大破.png
└── 皮肤/
    ├── 正常/
    │   └── {编号} {角色名} {皮肤名}-正常.png
    └── 大破/
        └── {编号} {角色名} {皮肤名}-大破.png
```

文件命名示例：`059 虎王-正常.png`、`059 虎王 冲浪行动-大破.png`

### 插件系统

- **插件生命周期**：完整的 load → activate → deactivate → unload 四阶段管理
- **线程包装**：插件运行在独立线程中，最大执行超时30秒，异常不影响主进程（非进程隔离）
- **权限控制**：12种权限分类，每个API调用前检查权限（read_settings/read_savegame/read_workspace/read_file_tree/access_editor/access_ui/access_network/access_filesystem/open_file/show_message/register_command/get_config）。**v1.6.6 安全加固**：MVP_READ_ONLY 改为实例属性防止插件篡改；register_command 使用原子操作防止竞态条件；get_config 返回只读视图，插件无法修改全局配置
- **PluginAPI**：提供open_file、show_message、register_command、get_config等接口
- **热加载**：支持不重启主程序的情况下更新插件
- **示例插件**：hello_panzer（生命周期 + 只读资源 API 示例）、word_counter（字数统计能力示例，展示编辑器交互权限）
- **⚠️ 可信插件模型**：当前插件系统是可信插件模型。插件代码运行在主程序进程中，权限系统只限制 PanzerNote 暴露的 API，不是完整安全沙箱。请只安装可信来源的插件。

### 主题系统

- **外部主题加载**：支持JSON/YAML格式的外部主题文件
- **主题解析引擎**：解析颜色方案、布局配置，自动生成QSS样式表
- **主题预览**：实时预览对话框，支持主题切换
- **全局生效**：所有UI组件通过ThemeAwareMixin订阅`theme_changed`信号，主题切换时自动更新样式（已集成11个组件：Editor/MarkdownPreviewWidget/EditorTabWidget/MinimapWidget/FileTreeWidget/FindReplaceBar/StatusBarWidget/SecretaryWidget/ResourceBar/GameSidebar/ShortcutPanel）

### 存档加密

- **加密算法**：PBKDF2密钥派生 + AES-GCM加密模式
- **密码验证**：支持密码正确性验证
- **自动迁移**：支持未加密存档向加密格式的无缝迁移，以及加密到明文的反向迁移
- **安全保存**：加密存档未解锁时跳过保存，防止默认数据覆写真实存档；关闭窗口时提示用户输入密码解锁

### 安全防护（v1.6.6 增强）

**本轮修复清单（v1.6.6 stable fixes）：**

- **QMessageBox 静态调用修正**：修正 `QMessageBox.Icon.*(...)` 枚举值误用为函数调用的问题，改为 `QMessageBox.warning()` / `.information()` 等静态方法
- **保存状态机**：保存任务不再立即标记 clean，明确 dirty→saving→clean/save_failed 状态流转，保存失败后恢复 dirty 状态
- **关闭时等待保存**：closeEvent 两阶段关闭，保存中不允许退出，保存失败中断关闭流程，全部成功后才最终关闭
- **临时会话恢复**：异常退出后保留 autosave session，重启时提示恢复，恢复提示在 window.show() 之后弹出
- **HTML/PDF 安全导出**：统一走 secure_markdown_renderer，纯文本 fallback 使用 html.escape()，禁用 script/iframe/onerror/javascript: 等危险内容
- **文件打开安全入口**：FileOpenService 统一校验文件打开来源（用户/拖放/插件/会话恢复/设置导入），分类控制路径白名单、扩展名和二进制检测
- **插件 API 边界收窄**：get_config() 返回 ReadOnlyConfigView 只读视图，open_file 走 FileOpenService.PLUGIN 路径校验，超时文案诚实说明无法强制终止线程
- **可信插件模型声明**：插件代码运行在主进程，权限系统仅限制暴露 API，非完整安全沙箱
- **状态栏信号驱动统计**：signal_driven_stats 默认开启，字符数使用 characterCount() 避免全文复制，词数 800ms 防抖统计，行列号由 cursorPositionChanged 驱动
- **搜索高亮修复**：普通搜索使用 QTextDocument.find() 获取权威光标位置，ExtraSelectionManager 统一管理高亮层避免互相覆盖，replace_all 从后向前逐匹配替换
- **Feature Flags 修正**：修复 \_FLAG_ALIASES 中 lazy_highlight→virtual_scroll 错误映射，signal_driven_stats/minimap_block_cache 默认开启，实验功能保持关闭
- **设置导入校验**：ConfigImportService 逐字段校验类型和值范围，非法字段跳过并报告，不再直接 \_settings.update()
- **依赖梳理**：pyproject.toml 分组 format/dev/all，所有运行时依赖均为必需
- **安全日志脱敏**：ErrorHandler 自动脱敏 password/token/secret/api_key/key 等敏感字段，日志中不出现明文凭据
- **增量渲染器命名澄清**：incremental_renderer.py 实际为全文 hash 渲染缓存（非真正 block 级增量渲染），README 不再宣称未实现能力
- **静态类型检查**：全项目通过 mypy 严格模式检查（0 error / 66 源文件），所有边界模块类型安全，消除 Optional 未判空、返回 Any、union-attr 等潜在运行时风险

### 版本管理

- **集中式版本源**：`src/__init__.py` 中的 `__version__` 为唯一真相源，所有模块通过引用获取版本号
- **动态版本配置**：`pyproject.toml` 通过 `setuptools.dynamic` 从 `src.__version__` 读取版本，无需硬编码
- **版本一致性验证**：`scripts/verify_version.py` 工具检查项目中所有版本号引用是否一致
- **启动时检查**：`main.py` 启动时自动验证版本一致性，不一致时记录警告日志

## 安装与运行

### 环境要求

- Python 3.11+
- Windows 10/11

### 安装依赖

```bash
pip install -e ".[format]"  # 完整安装（含格式化依赖）
pip install -e "."                  # 核心依赖（已包含预览功能）
```

> **可选依赖分组**：`format`（PyYAML/tomli/cssbeautifier）、`dev`（pytest/mypy）

### 运行

```bash
python main.py
```

## 目录结构

```
PanzerNote/
├── main.py                    # 程序入口（含启动时版本一致性检查）
├── requirements.txt           # 依赖列表
├── pyproject.toml             # 项目配置（pytest/mypy/依赖/动态版本引用）
├── .gitignore                 # Git 忽略规则（__pycache__/data/config/data/logs/等）
├── .gitattributes             # Git 属性（* text=auto eol=lf 行尾符统一）
├── user_data_path.txt         # 持久化用户数据路径
├── benchmarks/                # 性能基准测试
│   ├── __init__.py
│   ├── test_data_generator.py # 测试数据生成器
│   ├── benchmark_runner.py    # 基准测试运行器
│   ├── run_baseline.py        # 基线测试入口
│   ├── test_data/             # 生成的测试文件
│   └── results/               # 测试结果 JSON
├── tests/                     # 单元测试
│   ├── test_logger.py              # 结构化日志：初始化/控制台/文件/幂等性
│   ├── test_exceptions.py          # @safe_call装饰器：默认值/重新抛出/指定捕获
│   ├── test_event_bus.py           # 事件路由：信号连接/视图切换/文件操作
│   ├── test_timer_manager.py       # 定时器管理：创建/间隔/停止/回调
│   ├── test_game_engine.py         # 挂机收益：在线奖励/离线奖励/倍率/上限
│   ├── test_menu_builder.py        # 菜单构建：六菜单/菜单项/动作绑定
│   ├── test_editor_actions.py      # 编辑器行操作：删除/复制/上移/下移行
│   ├── test_auto_pair_handler.py   # 括号配对：英文/中文配对/右括号跳过
│   ├── test_config.py              # 配置管理：编辑器/游戏/资源/统计
│   ├── test_savegame_manager.py    # 存档管理器：加载/保存/加密状态/解锁数据恢复/每日签到
│   ├── test_first_run_dialog.py    # 首次运行：初始化/路径/目录创建
│   ├── test_game_sidebar.py        # 游戏侧边栏：按钮/视图状态/信号
│   ├── test_highlight_themes.py    # 高亮主题：主题列表/格式/CSS/HTML
│   ├── test_resource_bar.py        # 资源栏：数值/颜色/刷新/统计
│   ├── test_secretary_widget.py    # 小秘书：气泡/消息/事件台词
│   ├── test_status_bar.py          # 状态栏：标签/统计/编码/文件类型
│   ├── test_syntax_highlighter.py  # 语法高亮：Markdown标题/代码/粗体/链接
│   ├── test_dpi_helper.py          # 高DPI缩放：因子/尺寸/字体/样式表
│   ├── test_error_handler.py       # 错误提示：路径/IP/密码过滤/分类
│   ├── test_shortcut_manager.py    # 快捷键：注册/回调/冲突/持久化
│   ├── test_path_validator.py      # 路径安全：规范化/穿越检测/白名单
│   ├── test_file_guard.py          # 文件安全：读写/大小限制/超时
│   ├── test_crypto_manager.py      # 存档加密：加解密/密码/迁移
│   ├── test_input_validator.py     # 输入验证：文件名/保留名/搜索/设置
│   ├── test_plugin_system.py       # 插件基础：状态/权限/元数据/沙箱
│   ├── test_plugin_manager.py      # 插件管理：扫描/加载/热加载/验证
│   ├── test_theme_system.py        # 主题系统：颜色/布局/QSS生成/预览
│   ├── test_feature_flags.py       # Feature Flag：已注册flag/未注册flag警告/默认值
│   └── test_virtual_scroll.py      # 虚拟滚动：大文件加载/异常回退/边界情况
├── src/                       # 源代码
│   ├── __init__.py            # 版本号唯一真相源（__version__/get_version/get_version_tuple）
│   ├── main_window.py         # 主窗口（已拆分，v1.6.6：拖放文件类型白名单/分屏语义优化）
│   ├── core/                  # 核心模块
│   │   ├── config.py          # 配置管理（组合SavegameManager + SecurityManager）
│   │   ├── config_import_service.py # 配置导入服务（类型校验 + 白名单）
│   │   ├── savegame_manager.py # 存档管理器（加载/保存/加密状态/SavegameSaveResult枚举/每日签到）
│   │   ├── security_manager.py # 安全管理器（PathValidator/FileGuard/InputValidator集成）
│   │   ├── timer_manager.py   # 定时器管理中心
│   │   ├── event_bus.py       # 事件路由系统
│   │   ├── menu_builder.py    # 菜单构建器（v1.6.6：分屏菜单语义更新）
│   │   └── shortcut_manager.py # 快捷键管理器
│   ├── editor/                # 编辑器模块
│   │   ├── editor.py          # 文本编辑器（546行，已拆分，v1.6.6：insertFromMimeData粘贴检测/Backspace优化）
│   │   ├── editor_tabs.py     # 标签页管理（v1.6.6：IME粘贴误判修复/粘贴阈值提升/异步保存）
│   │   ├── editor_actions.py  # 行操作、大小写转换、格式化
│   │   ├── auto_pair_handler.py # 括号/引号自动配对（v1.6.6 性能优化：frozenset快速过滤/单字符访问/选区包裹优化）
│   │   ├── save_task.py        # 后台文件保存任务（v1.6.6 新增：QThreadPool异步写入）
│   │   ├── save_task_manager.py # 保存任务管理器（dirty→saving→clean/save_failed 状态机）
│   │   ├── temp_session_manager.py # 临时会话恢复（异常退出 autosave session 恢复）
│   │   ├── virtual_scroll.py  # 虚拟滚动管理器
│   │   ├── async_highlight.py # 异步代码高亮渲染器
│   │   ├── incremental_renderer.py # Markdown渲染缓存（全文 hash 缓存，非 block 级增量渲染）
│   │   ├── syntax_highlighter.py # 语法高亮
│   │   ├── highlight_themes.py # 代码高亮主题管理
│   │   ├── markdown_preview.py # Markdown分屏预览（v1.7.0：源码行号同步替代百分比同步/图片加载重同步）
│   │   ├── minimap.py         # 代码缩略图（v1.6.6：块级缓存增量失效）
│   │   ├── find_replace.py    # 增强型查找替换栏
│   │   ├── search_service.py  # 搜索服务（QTextDocument.find 权威光标 + 从后向前逐匹配替换）
│   │   ├── extra_selection_manager.py # 高亮层管理（统一 ExtraSelection 避免互相覆盖）
│   │   ├── secure_markdown_renderer.py # 安全 Markdown 渲染（统一清洗 script/iframe/onerror/javascript:）
│   │   ├── export_service.py  # 导出服务（HTML/PDF 统一安全管线）
│   │   ├── file_open_service.py # 文件打开安全入口（来源校验/路径白名单/二进制检测）
│   │   ├── editor_settings_dialog.py # 记事本设置对话框
│   │   ├── file_tree.py       # 文件树
│   │   └── status_bar.py      # 状态栏（signal_driven_stats：字符数 O(1)/词数防抖）
│   ├── game/                  # 游戏模块
│   │   ├── game_engine.py     # 挂机收益计算引擎
│   │   ├── resource_bar.py    # 资源栏
│   │   ├── game_sidebar.py    # 游戏侧边栏
│   │   └── secretary_widget.py # 小秘书组件
│   ├── ui/                    # UI组件
│   │   ├── first_run_dialog.py # 首次运行对话框
│   │   └── shortcut_panel.py  # 快捷键提示面板
│   ├── security/              # 安全模块
│   │   ├── __init__.py        # 安全模块导出与异常定义
│   │   ├── path_validator.py  # 路径安全验证（规范化/白名单/穿越防护）
│   │   ├── file_guard.py      # 文件操作安全控制（大小限制/超时控制）
│   │   ├── file_access_context.py # 文件访问上下文（来源枚举 + 权限分级）
│   │   ├── crypto_manager.py  # 存档加密系统（PBKDF2+AES-GCM/迁移/备份）
│   │   ├── input_validator.py # 输入验证框架（文件名/搜索/设置值）
│   ├── plugins/               # 插件系统
│   │   ├── __init__.py        # 插件系统导出
│   │   ├── plugin_base.py     # 插件基类与元数据定义（min_app_version引用集中版本）
│   │   ├── plugin_api_views.py # 插件 API 只读视图（ReadOnlyConfigView 防止插件越权修改配置）
│   │   ├── plugin_sandbox.py  # 插件包装器（线程隔离/超时/权限控制/PluginAPI含open_file/show_message/register_command/get_config，v1.6.6安全加固）
│   │   ├── plugin_manager.py  # 插件管理器（扫描/加载/热加载）
│   │   └── plugin_manager_dialog.py # 插件管理对话框
│   ├── themes/                # 主题系统
│   │   ├── __init__.py        # 主题系统导出
│   │   ├── theme_engine.py    # 主题引擎（加载/解析/样式生成）
│   │   ├── theme_aware_mixin.py # 主题感知混入（组件订阅theme_changed信号）
│   │   └── theme_preview.py   # 主题预览对话框
│   └── utils/                 # 工具模块
│       ├── __init__.py        # 工具模块导出
│       ├── logger.py          # 结构化日志系统
│       ├── exceptions.py      # 统一异常处理 @safe_call
│       ├── error_handler.py   # 统一错误提示系统
│       ├── dpi_helper.py      # 高DPI缩放适配
│       ├── feature_flags.py   # Feature Flag 系统
│       ├── lazy_loader.py     # 启动性能分析（StartupProfiler阶段计时）
├── scripts/                   # 工具脚本
│   └── verify_version.py     # 版本一致性验证工具
├── data/
│   ├── assets/
│   │   ├── portraits/          # 角色立绘
│   │   └── icons/              # 图标
│   └── gamedata/              # 游戏数据
├── plugins/                   # 插件目录
│   ├── hello_panzer/          # 基础功能示例插件
│   │   ├── plugin.json        # 插件清单
│   │   └── main.py            # 插件入口
│   ├── word_counter/          # UI扩展示例插件
│   │   ├── plugin.json        # 插件清单
│   │   └── main.py            # 插件入口
│   └── plugin_api.md          # 插件开发技术文档
└── notebooks/                 # 用户笔记
```

## 单元测试

项目共 29 个测试文件，覆盖核心模块、编辑器、游戏系统、安全模块及可扩展性架构。

### 运行测试

```bash
pip install pytest pytest-qt pytest-cov
pytest tests/ -v
```

### 测试文件说明

| 测试文件                   | 测试目的            | 预期验证的功能点                                                                                          |
| -------------------------- | ------------------- | --------------------------------------------------------------------------------------------------------- |
| test_logger.py             | 结构化日志系统      | 初始化创建 `src` 前缀 logger；文件日志写入 `panzernote.log`；幂等性不重复添加 handler                     |
| test_exceptions.py         | `@safe_call` 装饰器 | 正常函数返回原值；异常时返回 `default`；`reraise=True` 重新抛出；`catch` 仅捕获指定类型                   |
| test_event_bus.py          | 事件路由系统        | `connect_signals` 连接所有 UI 信号；视图切换正确；文件保存更新状态                                        |
| test_timer_manager.py      | 定时器管理器        | 创建自动保存/统计/挂机三个定时器；动态调整间隔；`stop_all` 停止所有；回调异常不崩溃                       |
| test_game_engine.py        | 挂机收益引擎        | 基础奖励 fuel/ammo/steel 各 5；铝材计数控制；倍率乘算；离线 ≥5 分钟计算；24 小时上限                      |
| test_menu_builder.py       | 菜单构建器          | 生成六大菜单；文件/编辑菜单项完整；动作触发对应方法                                                       |
| test_editor_actions.py     | 编辑器行操作        | 删除行/复制行/上移行/下移行正确执行；边界条件处理                                                         |
| test_auto_pair_handler.py  | 括号自动配对        | 英文/中文括号配对；右括号跳过；设置开关控制                                                               |
| test_config.py             | 配置管理器          | 编辑器/游戏设置持久化；资源 CRUD；打字统计跨日归零                                                        |
| test_savegame_manager.py   | 存档管理器          | 加密/未加密存档加载；SavegameSaveResult枚举；加密未读状态跳过保存；解锁后数据恢复；加密文件备份；每日签到 |
| test_first_run_dialog.py   | 首次运行对话框      | 窗口标题/默认路径正确；确认后创建目录结构                                                                 |
| test_game_sidebar.py       | 游戏侧边栏          | 按钮初始化；`set_current_view` 高亮；信号发射                                                             |
| test_highlight_themes.py   | 代码高亮主题        | 主题列表/获取/格式构建/预览 CSS/代码高亮 HTML                                                             |
| test_resource_bar.py       | 资源栏组件          | 资源项颜色映射；数值设置/刷新/打字统计                                                                    |
| test_secretary_widget.py   | 小秘书组件          | 气泡显示/隐藏；消息显示；事件台词匹配                                                                     |
| test_status_bar.py         | 状态栏组件          | 默认标签文本；统计/编码/文件类型更新                                                                      |
| test_syntax_highlighter.py | 语法高亮器          | Markdown 标题/代码块/行内代码/粗体/链接/列表/引用                                                         |
| test_dpi_helper.py         | 高 DPI 缩放         | 缩放因子范围；整数/尺寸/字体/样式表缩放；幂等性                                                           |
| test_error_handler.py      | 错误提示系统        | 路径/IP/密码/token 过滤；分类标签/建议映射完整                                                            |
| test_shortcut_manager.py   | 快捷键管理器        | 默认加载/注册/回调/冲突检测/持久化                                                                        |
| test_path_validator.py     | 路径安全验证        | 规范化/目录穿越检测/白名单/路径长度/控制字符                                                              |
| test_file_guard.py         | 文件操作安全        | 安全读写往返一致；大小限制/超时控制                                                                       |
| test_crypto_manager.py     | 存档加密系统        | 加密-解密往返；错误密码/损坏数据异常；中文数据；迁移备份                                                  |
| test_input_validator.py    | 输入验证框架        | 文件名验证/保留名拒绝/搜索注入防护/设置值范围                                                             |
| test_plugin_system.py      | 插件基础架构        | 状态/权限枚举；元数据序列化；生命周期；沙箱权限检查                                                       |
| test_plugin_manager.py     | 插件管理器          | 扫描/加载/激活/停用/卸载/热加载/清单验证/版本兼容                                                         |
| test_theme_system.py       | 主题系统            | 颜色方案/布局配置/主题定义/引擎加载/QSS 生成                                                              |
| test_feature_flags.py      | Feature Flag 系统   | 已注册 flag 返回正确值；未注册 flag 返回 False 并记录警告；配置文件加载/无效JSON容错                      |
| test_virtual_scroll.py     | 虚拟滚动管理器      | 大文件返回 True 并激活虚拟滚动；`setPlainText` 异常回退普通模式；阈值边界；Unicode 处理                   |

## 快捷键

> 快捷键支持自定义，可在快捷键提示面板（`Ctrl+/`）中查看和修改。系统会自动检测快捷键冲突。

### 文件操作

| 快捷键       | 功能         |
| ------------ | ------------ |
| Ctrl+N       | 新建文件     |
| Ctrl+O       | 打开文件     |
| Ctrl+S       | 保存         |
| Ctrl+Shift+S | 另存为       |
| Ctrl+W       | 关闭当前标签 |

### 编辑操作

| 快捷键          | 功能               |
| --------------- | ------------------ |
| Ctrl+Z          | 撤销               |
| Ctrl+Y          | 重做               |
| Ctrl+X / C / V  | 剪切 / 复制 / 粘贴 |
| Ctrl+A          | 全选               |
| Tab / Shift+Tab | 增加 / 减少缩进    |

### 查找与导航

| 快捷键        | 功能                |
| ------------- | ------------------- |
| Ctrl+F        | 查找                |
| Ctrl+H        | 替换                |
| Ctrl+G        | 转到行              |
| F3 / Shift+F3 | 查找下一个 / 上一个 |

### 行操作

| 快捷键       | 功能       |
| ------------ | ---------- |
| Ctrl+Shift+K | 删除当前行 |
| Alt+↑        | 上移当前行 |
| Alt+↓        | 下移当前行 |
| Ctrl+Shift+D | 复制当前行 |

### 大小写转换

| 快捷键       | 功能                    |
| ------------ | ----------------------- |
| Ctrl+Shift+U | 切换大小写（大写↔小写） |

### 视图操作

| 快捷键          | 功能                |
| --------------- | ------------------- |
| Ctrl+B          | 折叠/展开文件树     |
| Ctrl+M          | 显示/隐藏代码缩略图 |
| Ctrl+Shift+P    | 切换Markdown预览    |
| Ctrl+/          | 快捷键提示面板      |
| Ctrl++ / Ctrl+- | 放大 / 缩小         |
| Ctrl+0          | 重置缩放            |
| F11             | 全屏                |

## 设置项

可在「设置 → 记事本设置」对话框中配置：

| 设置项            | 说明                              | 默认值            |
| ----------------- | --------------------------------- | ----------------- |
| 显示行号          | 编辑器左侧显示行号                | 开启              |
| 高亮当前行        | 当前光标所在行浅黄色背景          | 开启              |
| 显示缩略图        | 编辑器右侧代码缩略图              | 开启              |
| 自动开关缩略图    | 勾选后.txt和.md不显示缩略图       | 关闭              |
| 括号/引号自动配对 | 输入英文/中文括号与引号时自动补全 | 开启              |
| 字体              | 从本地字体库选择编辑器字体        | Microsoft YaHei   |
| 字体大小          | 编辑器字体大小                    | 12pt              |
| 行宽模式          | 不换行 / 限制行宽                 | 不换行            |
| 自动保存间隔      | 自动暂存间隔（秒）                | 30秒              |
| 显示小秘书        | 右下角显示角色立绘和台词气泡      | 开启              |
| 小秘书尺寸占比    | 占窗口面积百分比（3%~20%）        | 7%                |
| 代码高亮主题      | 需在 `settings.json` 中配置       | `"pycharm_light"` |

### 安全配置

| 参数                        | 位置                 | 说明                               | 默认值 |
| --------------------------- | -------------------- | ---------------------------------- | ------ |
| `max_file_size`             | `FileGuard` 构造参数 | 文件大小上限（字节），超过拒绝读取 | 50MB   |
| `timeout`                   | `FileGuard` 构造参数 | 文件操作超时（秒），超时自动中断   | 15s    |
| `MAX_PATH_LENGTH`           | `PathValidator`      | 路径长度上限                       | 260    |
| `MAX_FILENAME_LENGTH`       | `InputValidator`     | 文件名长度上限                     | 255    |
| `MAX_SEARCH_LENGTH`         | `InputValidator`     | 搜索内容长度上限                   | 10000  |
| `MAX_SETTING_STRING_LENGTH` | `InputValidator`     | 设置字符串长度上限                 | 1000   |
| PBKDF2 迭代次数             | `CryptoManager`      | 密钥派生迭代次数                   | 600000 |
| AES-GCM 密钥长度            | `CryptoManager`      | 加密密钥长度（字节）               | 32     |

新增主题：在 `src/highlight_themes.py` 的 `THEMES` 字典中添加条目即可。

## 更新日志

### v1.7.0

**Markdown 预览滚动同步改造**

- **源码行号同步替代百分比同步**：将 Markdown 预览同步方式从"滚动条百分比同步"改为"源码行号到预览 DOM 锚点同步"。编辑器滚动时获取当前顶部源码行号，通过 JS 查找预览 HTML 中最接近的 `data-source-line` 节点并滚动到对应位置
- **源码行号注入渲染**：新增 `_render_markdown_with_source_map()` 方法，使用 markdown-it-py 的 `token.map` 给块级 HTML 节点注入 `data-source-line` 属性，覆盖标题、段落、引用、列表、表格、代码块、分割线等 token 类型
- **代码块源码行号保留**：`_build_container()` 和 `_process_code_blocks()` 支持传入 `source_line` 参数，代码块外层容器携带 `data-source-line` 属性，确保代码块区域也能精准同步
- **JS 插值同步算法**：HTML 模板注入 `scrollToSourceLine()` 函数，在相邻两个锚点节点之间做线性插值，改善长表格、长列表、长代码块的同步体验
- **图片加载后重同步**：HTML 模板注入 `resyncAfterImagesLoaded()` 函数，图片加载完成或失败后自动重新同步预览位置，避免图片撑开页面导致错位
- **QTextBrowser fallback 保留**：QWebEngineView 使用源码行号同步，QTextBrowser 继续使用旧百分比同步（无 DOM 查询能力）

### v1.6.6

**性能优化、安全加固与Bug修复**

- **自动配对性能优化**（A.1）：重构 `auto_pair_handler.py`，引入 `frozenset` 快速过滤机制，非括号/引号字符 O(1) 返回，不再读取光标或全文；新增 `_doc_char_at()` 按需访问文档单字符，替代 `toPlainText()` 全文复制；新增 `_ensure_auto_pair_cache()` 惰性加载字符集缓存，仅在 `AUTO_PAIR_CHARS` 变更时重建；`_pick_single_cjk_quote` 改用 `QTextCursor` 读取前缀，替代 `toPlainText()` + 切片；行内引号计数改用 `block.text()` + `str.count(start, end)`，替代全文切片
- **选区包裹优化**（A.2）：新增 `_wrap_selection()` 方法，使用 `QTextCursor` 操作包裹选区，避免 `selectedText()` 大字符串复制。4处调用点统一使用新方法
- **MarkdownIt 实例复用**（B.1/PERF-002）：`MarkdownPreviewWidget` 新增 `_create_md_parser()` 方法，在 `__init__` 中创建一次 MarkdownIt 解析器实例并缓存为 `_md_parser`，`_render_markdown()` 直接调用缓存的实例渲染，消除每次按键重复实例化 + 插件注册的开销（每次渲染节省 5-7ms，约 30-50% 提升）。deflist 插件 ImportError 增加 debug 日志
- **文件保存异步化**（B.2/PERF-003）：新建 `src/editor/save_task.py`（`SaveTask` + `SaveTaskSignals`），将 `safe_write` 磁盘 IO 放到 `QThreadPool` 后台线程执行。`EditorTabWidget._save_file()` 改为异步保存：主线程仍需 `toPlainText()` 获取内容，但磁盘写入在后台完成，UI 不再因大文件保存冻结。`save_all_to_temp()` 同步改为异步。保存失败时自动回滚修改状态并恢复标签页 `*` 标记
- **Markdown 预览增量更新**（B.3/PERF-007）：`PREVIEW_HTML_TEMPLATE` 新增 `<div id="content">` 包裹内容区。`MarkdownPreviewWidget` 新增 `_html_template_loaded` 标志，首次渲染走 `setHtml` 加载完整模板，后续渲染通过 `QWebEngineView.runJavaScript()` 仅更新 `innerHTML`，避免每次重建整个 DOM 树。切换文档（`base_path` 变化）时自动重置标志。`loadFinished` 信号触发后标记模板已加载
- **Minimap 块级缓存增量失效**（B.4/PERF-004）：`MinimapWidget` 改用 `QTextDocument.contentsChange` 信号（带 `from_pos/chars_removed/chars_added` 参数），精确计算受影响的缓存块范围并标记为脏块（`_block_dirty`），仅重新渲染脏块而非全部。行数变化时后续块也标记为脏，确保缓存索引一致。`_render_with_block_cache()` 改为跳过非脏缓存块，渲染后从 `_block_dirty` 中移除。常规打字（修改 1-2 行）时仅重绘 1 个块，节省约 95% 渲染开销
- **拖放文件类型白名单**（SEC-009）：`MainWindow` 新增 `_SUPPORTED_DROP_EXTS` 类属性，仅允许 `.txt`、`.md`、`.py`、`.c`、`.cpp`、`.h`、`.java`、`.js`、`.json`、`.html`、`.css`、`.xml`、`.yaml`、`.yml`、`.toml`、`.ini`、`.log`、`.sql`、`.sh`、`.go`、`.rs` 等文本文件类型。`dropEvent` 中对非白名单扩展名弹出警告对话框，防止意外打开二进制文件
- **PDF/HTML导出安全**（SEC-008）：Markdown转PDF和转HTML时均显式禁用原始HTML渲染（`MarkdownIt("commonmark", {"html": False})`），python-markdown fallback 仅启用 tables 扩展，防止XSS注入攻击
- **插件API防护**（SEC-010）：`PluginAPI` 的 `MVP_READ_ONLY` 从类变量改为实例属性 `_mvp_read_only`，防止恶意插件通过类级别篡改权限检查标志
- **命令注册竞态修复**（SEC-011）：`PluginAPI.register_command()` 使用 `dict.setdefault()` 原子操作替代先检查后插入的两步操作，消除 TOCTOU（Time-of-Check-to-Time-of-Use）竞态条件
- **IME打字奖励误判修复**（BUG-020）：`Editor` 新增 `_is_pasting` 标志，重写 `insertFromMimeData()` 在粘贴时设置标志；`EditorTabWidget._on_text_changed()` 增加 `is_pasting` 检查，粘贴操作不再计入打字奖励；粘贴检测阈值 `_PASTE_THRESHOLD` 从 15 提升至 50，避免 IME 整句输入被误判为粘贴
- **分屏语义优化**（BUG-021/022）：`_split_editor()` 改为打开新空白文件而非当前文件，避免两个标签页编辑同一文件导致数据覆盖风险；菜单文本更新为"水平分屏（独立编辑）"/"垂直分屏（独立编辑）"，明确语义
- **封装违规修复**（BUG-023）：`MainWindow._check_daily_checkin()` 中 `self.config._savegame_manager` 改为 `self.config.savegame_manager`，使用公开属性而非私有属性
- **行尾符统一**（BUG-024）：`editor.py`、`menu_builder.py`、`plugin_manager.py` 三个文件的 CRLF 行尾符统一转换为 LF，配合 `.gitattributes` 的 `* text eol=lf` 规则
- **Markdown预览主题修复**：`MarkdownPreviewWidget._apply_theme_colors()` 增加 `isinstance(self.preview, PreviewBrowser)` 类型检查，修复主题初始化顺序导致的 `AttributeError`
- **工程化改进**（INFRA-007）：`.gitignore` 新增 `data/logs/`、`Thumbs.db`、`scripts/__pycache__/` 条目
- **Silent except 日志补全**（QUAL-029）：7 个文件中的 `except ... : pass` 全部添加 debug/warning 日志，包括 `minimap.py`（AttributeError）、`markdown_preview.py`（ValueError/IndexError）、`editor_tabs.py`（ValueError）、`config.py`（Exception）、`exceptions.py`（兜底 print）、`plugin_base.py`（ValueError）、`find_replace.py`（re.error）、`plugin_manager.py`（Exception）
- **主题切换响应完善**（QUAL-031）：`MainWindow._apply_theme()` 新增 `_game_placeholder` 样式更新；`FindReplaceBar._apply_theme_colors()` 末尾调用 `_update_match_label()` 确保匹配计数标签颜色随主题同步
- **ErrorHandler 正则收紧**（QUAL-033）：`_SENSITIVE_PATTERNS` 中 `File "..."` 和 `line N` 两条独立正则合并为 `File "...", line N`，避免误过滤"on line 10""第 5 行"等普通文案

**兼容性说明**

- 所有改动向后兼容，无需迁移现有配置或存档
- `_SUPPORTED_DROP_EXTS` 白名单可通过修改 `MainWindow` 类属性扩展，不影响已有功能
- `_is_pasting` 标志对非粘贴输入（键盘/IME）无影响，打字奖励逻辑仅在粘贴时跳过计数
- 分屏行为变更：旧版本分屏打开当前文件的副本，新版本分屏打开空白文件。此为破坏性变更，但旧行为存在数据覆盖风险，新行为更安全
- 文件保存异步化：保存操作不再阻塞 UI，但保存失败时标签页会恢复修改标记。调用方（`_save_current`/`_save_all`）的返回值语义不变，但磁盘写入实际在后台完成
- Markdown 增量更新仅对 QWebEngineView 有效，QTextBrowser（PreviewBrowser）模式仍走全量 setHtml 路径

### v1.6.5

**架构整改与安全修复**

- **Config 职责拆分**：将 `config.py` 中的存档管理和安全管理逻辑拆分为独立类。新建 `core/savegame_manager.py`（`SavegameManager`），负责存档加载/保存/加密状态/资源CRUD；新建 `core/security_manager.py`（`SecurityManager`），负责路径验证/文件操作安全/输入验证的集成管理。`Config` 类通过组合方式委托调用，保持对外接口兼容
- **数据存储抽象层移除**：删除 `src/storage/` 目录（`storage_interface.py`/`json_storage.py`/`sqlite_storage.py`/`storage_factory.py`/`storage_migrator.py`），因全项目无业务调用方。`test_storage.py` 已一并移除
- **LazyLoader 移除**：`LazyLoader` 类（register/get/add_deferred_init/run_deferred_inits）全项目无调用方，已移除。仅保留 `StartupProfiler` 启动性能分析器，阶段管理集中到 `main.py`
- **PluginManagerDialog 提取**：从 `plugin_manager.py` 中提取 `PluginManagerDialog` 为独立模块 `plugin_manager_dialog.py`，降低单文件复杂度
- **主题系统全局生效**：新建 `themes/theme_aware_mixin.py`（`ThemeAwareMixin`），所有 UI 组件通过继承此 Mixin 订阅 `theme_changed` 信号，主题切换时自动更新样式。编辑器和 Markdown 预览中的硬编码颜色已改为主题系统变量
- **加密存档保存逻辑修复**（SEC-003）：`SavegameManager.save()` 新增 `SavegameSaveResult` 枚举返回值（`SUCCESS`/`SKIPPED_ENCRYPTED_UNREAD`/`ENCRYPTION_FAILED`），加密但未解锁的存档返回 `SKIPPED_ENCRYPTED_UNREAD` 而非静默跳过。MainWindow 在关闭时检查此状态并弹出密码输入对话框，供用户解锁存档后保存
- **加密存档解锁数据恢复**：修复 `set_encryption_password()` 在从加密未读状态解锁时，未重新加载原始加密数据导致内存数据为默认值的安全隐患。解锁时现在自动调用 `decrypt_savegame()` 加载原始数据，密码错误则恢复加密未读状态
- **加密存档加载安全备份**：`load()` 在进入加密未读状态（无密码或解密失败）时，自动备份加密文件（`.encrypted.bak`），作为数据恢复安全网
- **SavegameManager 重复初始化修复**：`Config.__init__()` 中创建 `SavegameManager` 实例后，`_load_all()` 不再重复创建新实例，仅调用 `load()` 加载数据，避免状态不一致
- **版本号统一引用**：所有版本号引用统一使用 `from src import __version__`，消除硬编码字符串
- **集中式版本管理**：`src/__init__.py` 新增 `get_version()` 和 `get_version_tuple()` 工具函数，作为版本号唯一真相源。`pyproject.toml` 改用 `dynamic = ["version"]` + `setuptools.dynamic` 从 `src.__version__` 动态读取版本。`plugin_base.py` 的 `min_app_version` 默认值改为引用 `_app_version`，插件示例文件同步更新。新建 `scripts/verify_version.py` 版本一致性验证工具，`main.py` 启动时自动检查版本一致性
- **每日签到**：`SavegameManager` 新增 `check_daily_checkin()` 方法，每日首次启动自动发放签到奖励（燃料/弹药/钢材/铝材各+100），通过小秘书提示

### v1.6.4

**阶段五：可扩展性架构及重构实施**

- **插件接口规范**：新建 `plugins/plugin_base.py`，定义完整插件生命周期（load/activate/deactivate/unload）、元数据规范（PluginMeta）、权限枚举（PluginPermission），最低兼容版本默认 1.6.4
- **插件沙箱隔离**：新建 `plugins/plugin_sandbox.py`，实现插件运行隔离（独立线程执行）、超时控制（默认30秒）、权限检查（MVP阶段严格只读访问），未授权访问抛出 `SandboxViolationError`，超时抛出 `SandboxTimeoutError`
- **插件管理系统**：新建 `plugins/plugin_manager.py`，实现从 `plugins/` 目录递归扫描插件包、验证清单完整性（plugin.json 必需字段）、插件注册/激活/停用/卸载管理接口、热加载机制（reload_plugin 不重启更新插件）
- **示例插件**：新建 `plugins/hello_panzer/`（基础功能插件，展示生命周期和只读API）和 `plugins/word_counter/`（UI扩展插件，展示编辑器交互和状态栏集成）
- **插件API文档**：新建 `plugins/plugin_api.md`，包含完整的插件开发指南、权限系统说明、沙箱隔离规范、PluginAPI接口参考和示例代码
- **主题系统**：新建 `themes/theme_engine.py`，支持JSON/YAML格式外部主题加载、颜色方案解析、QSS样式表自动生成、主题切换覆盖所有UI元素。新建 `themes/theme_preview.py`，提供主题预览对话框和实时预览功能
- **数据存储抽象层**：新建 `storage/storage_interface.py`，定义IStorage接口（CRUD/事务/元数据操作标准方法）。新建 `storage/json_storage.py`（JSON文件存储适配器）和 `storage/sqlite_storage.py`（SQLite数据库存储适配器）。新建 `storage/storage_factory.py`（存储实现工厂）和 `storage/storage_migrator.py`（存储间数据迁移工具）
- **主窗口集成**：修改 `main_window.py`，在启动流程中初始化主题引擎和插件管理器，菜单栏新增主题管理和插件管理入口
- **单元测试**：新增 `test_plugin_system.py`、`test_plugin_manager.py`、`test_theme_system.py`，覆盖插件生命周期、沙箱隔离、主题加载解析

### v1.6.3

**阶段四：系统安全性强化与防护机制建设**

- **路径安全验证模块**：新建 `security/path_validator.py`，实现路径规范化（`os.path.realpath`）、安全路径白名单机制、目录穿越攻击防护（`../`/`..\\` 检测）。支持 Windows 大小写不敏感文件系统和 `\\?\` 长路径前缀处理，路径长度限制 260 字符，控制字符检测
- **文件操作安全控制**：新建 `security/file_guard.py`，实现文件大小限制机制（默认 50MB，可配置）和操作超时控制（默认 30 秒）。使用线程实现超时中断与资源释放，正确处理符号链接和稀疏文件的大小计算，禁止使用 `os.path.getsize` 简单检测
- **存档数据加密系统**：新建 `security/crypto_manager.py`，基于用户密码使用 PBKDF2（600,000 次迭代）派生密钥，采用 AES-GCM 加密模式保护 `savegame.json`。支持未加密存档向加密格式的无缝迁移，迁移前自动备份，迁移后验证数据一致性。提供密码验证和加密状态检测接口
- **输入验证统一框架**：新建 `security/input_validator.py`，实现文件名验证（过滤非法字符、Windows 保留名称、路径注入、长度限制 255）、搜索内容验证（XSS/注入模式检测、长度限制 10,000）、设置值验证（类型检查、范围限制、允许值列表）。提供 `sanitize_filename` 清洗接口
- **安全模块集成**：修改 `config.py`、`editor_tabs.py`、`file_tree.py`、`find_replace.py`，所有文件操作通过 `FileGuard` 安全读写，新建/重命名文件通过 `InputValidator` 验证，搜索内容通过注入检测，存档支持加密/解密
- **单元测试**：新增 `test_path_validator.py`、`test_file_guard.py`、`test_crypto_manager.py`、`test_input_validator.py`，安全模块测试覆盖率达 93%

**Bug 修复**

- **修复窗口无法缩放**：修正 `dpi_helper.py` 中 `init_dpi()` 的双重缩放问题。当 `Qt.AA_EnableHighDpiScaling` 已启用时，Qt 自动处理 DPI 缩放，`scale()` 不应再乘以 `devicePixelRatio`，否则 `setMinimumSize(scale(800), scale(600))` 在 200% 缩放下变为 1600×1200，超出屏幕分辨率导致窗口无法调整大小
- **修复小秘书组件尺寸过大**：重构 `secretary_widget.py` 尺寸机制，从固定像素值（210×380）改为基于窗口面积的百分比控制。默认占窗口面积 7%，范围 3%~20%，可在「记事本设置 → 小秘书」中通过滑块调节，设置实时生效并持久化保存。小秘书随窗口缩放自动重新计算尺寸，保持 210:380 宽高比

**阶段三：用户体验提升优化与实现**

- **高 DPI 适配**：新建 `utils/dpi_helper.py`，实现基于 `devicePixelRatio` 的动态缩放机制。应用启动时自动启用 `Qt.AA_EnableHighDpiScaling`，所有视觉元素尺寸使用相对单位（`scale()`/`scale_size()`/`scale_font()`/`scale_stylesheet()`），支持 100%~200% 缩放比例下正常显示
- **小秘书位置跟随重构**：重构 `secretary_widget.py` 位置跟踪逻辑，使用 `eventFilter` 实时监听父容器 `resize`/`move` 事件，采用防抖机制（≤50ms）避免频繁更新，动态位置计算算法确保立绘始终右下对齐且不越界，支持窗口最大化/最小化/任意尺寸调整/多显示器拖动
- **快捷键系统**：新建 `core/shortcut_manager.py`，实现快捷键注册、冲突检测（系统级 + 应用内部）、自定义修改与持久化。`MenuBuilder` 已接入 `ShortcutManager`，所有菜单项通过 `manager.register()` 注册，用户在快捷键面板自定义的快捷键能真正生效。新建 `ui/shortcut_panel.py` 快捷键提示面板（`Ctrl+/` 调出），支持搜索、按功能模块分类展示、双击编辑快捷键。`settings.json` 新增 `shortcuts` 配置段
- **错误提示系统优化**：新建 `utils/error_handler.py`，实现统一错误处理中间层。8 类错误分类（文件/网络/配置/游戏/编辑器/权限/内存/通用），每类含默认建议操作。敏感信息过滤（路径/堆栈/IP/密码/Token），确保不泄露内部信息。自定义错误处理器注册机制，支持回退到默认对话框
- **单元测试**：新增 `test_dpi_helper.py`、`test_error_handler.py`、`test_shortcut_manager.py`，阶段三新增模块测试覆盖率达 93%

### v1.6.2

**阶段一：基础设施与代码质量重构**

- **结构化日志系统**：新建 `utils/logger.py`，统一日志级别（DEBUG/INFO/WARNING/ERROR）、格式（时间戳+模块+级别+消息）、输出位置（控制台 + 滚动文件，单文件最大5MB，保留3个备份）。日志目录自动创建，集成到 `main.py` 启动流程
- **统一异常处理装饰器 `@safe_call`**：新建 `utils/exceptions.py`，实现 `@safe_call` 装饰器自动捕获异常并记录日志。替换项目中所有 `except Exception: pass` 和 `except: pass` 模式，确保异常不再被静默吞掉。修复了重构过程中发现的 `QMessageBox` 参数错误
- **main_window.py 模块拆分**（1099行 → 677行）：
  - `game/game_engine.py`：挂机收益计算引擎（在线/离线奖励、资源上限检查）
  - `core/timer_manager.py`：定时器管理中心（自动保存、统计更新、挂机奖励定时器统一管理）
  - `core/event_bus.py`：事件路由系统（信号连接集中管理，解耦各模块间通信）
  - `core/menu_builder.py`：菜单构建器（菜单栏构建逻辑提取，支持动态菜单项）
- **editor.py 模块拆分**（1152行 → 546行）：
  - `editor/editor_actions.py`：行操作（删除/上移/下移/复制行）、大小写转换、JSON/XML格式化
  - `editor/auto_pair_handler.py`：括号/引号自动配对逻辑（Mixin模式，支持中英文标点）
- **类型提示与 mypy 集成**：为所有重构模块添加完整类型提示，在 `pyproject.toml` 中配置 mypy，配置 Mixin 模式的类型检查豁免规则
- **pytest 测试框架搭建**：安装 pytest/pytest-cov/pytest-qt，创建 `pyproject.toml` 配置，编写 187 个单元测试覆盖所有重构模块，核心模块覆盖率达 30.7%

**阶段二：性能优化攻坚**

- **editor.py 虚拟滚动**：新建 `editor/virtual_scroll.py`，实现 `VirtualScrollManager`。仅渲染当前可视区域内容，上下各保留 BUFFER_LINES 行缓冲区。大文件（≥50000行）自动启用延迟语法高亮，仅高亮可视区域及缓冲区内的代码块。滚动时通过 `QTimer.singleShot` 延迟触发高亮更新，避免滚动过程中阻塞渲染
- **minimap.py 渲染优化**：重构 `_render_content()` 方法，实现块级缓存（BLOCK_SIZE=50行/块）+ 批量渲染。使用 `QPicture` 缓存每个块的渲染结果，仅在内容变更时标记对应缓存块为脏块并重新渲染。将逐字符渲染改为按颜色分段批量绘制，显著减少 `QPainter` 状态切换次数
- **highlight_code_html() 异步渲染**：新建 `editor/async_highlight.py`，实现 `HighlightWorker`（QThread）和 `AsyncHighlightRenderer`。渲染工作在后台线程执行，主线程通过 `Qt.ConnectionType.QueuedConnection` 信号接收结果。支持最多 2 个并发渲染线程、任务优先级队列、10秒超时自动取消、渲染结果 LRU 缓存（50条）。集成到 `markdown_preview.py`，先渲染占位符再异步替换高亮结果
- **markdown_preview.py 增量渲染优化**：新建 `editor/incremental_renderer.py`，实现 `IncrementalRenderer` 和 `LRUCache`。基于 MD5 哈希的渲染结果缓存（容量50），相同文本直接返回缓存。行级变更检测，仅当文本实际变更时才重新调用渲染函数。代码块懒加载：异步模式下先显示纯文本占位，高亮完成后替换
- **应用启动性能优化**：新建 `utils/lazy_loader.py`，实现 `StartupProfiler` 启动性能分析器。`main.py` 中延迟导入 MainWindow，各初始化阶段加入性能分析标记。`_restore_state()` 改为延迟打开文件：先打开第一个文件使窗口快速呈现，剩余文件通过 `QTimer.singleShot(0)` 在事件循环空闲时逐个加载（原 `LazyLoader` 类已移除，因无业务调用方）
- **性能基准测试体系**：创建 `benchmarks/` 目录，包含 `test_data_generator.py`（生成小型500行/中型5000行/大型50000行测试文件）和 `run_baseline.py`（自动化基准测试运行器）。测量指标包括：文件打开时间、滚动FPS、缩略图渲染时间、代码高亮时间、内存占用、启动时间
- **Feature Flag 系统**：新建 `utils/feature_flags.py`，实现 5 个性能优化开关（`virtual_scroll`/`minimap_block_cache`/`async_highlight`/`markdown_incremental`/`lazy_loading`），默认全部关闭使用旧有实现路径。配置持久化到 `feature_flags.json`，支持运行时动态切换

### v1.6.1

- **修复：括号/引号自动配对崩溃bug**：修复在两字符中间输入括号后删除再输入中文引号时程序崩溃的严重问题（退出码 0xC0000409），将内联函数 `_pick_single_cjk_quote` 提取为类方法以解决作用域冲突
- **修复：自动配对触发条件过于宽松**：将"任意一侧有括号/引号就自动配对"改为"仅当光标左右恰好是互相匹配的一对符号时才自动配对"，避免在 `）你` 等单侧括号/引号旁误触发配对
- **新增：智能光标定位**：在单独左括号/引号（如 `(`）后输入对应右括号/引号（如 `)`）时，自动将光标移到符号中间，方便连续输入

### v1.6

- **新增：括号/引号自动配对：支持英文 () [] {} "" '' 与中文 （）【】「」『』《》〈〉“”‘’；中文输入法（IME）输入中文标点同样生效；支持“已有配对符号之间继续输入并自动补全”的嵌套输入；右括号/右引号可跳过已有同字符；Backspace 支持成对删除；选中文本时输入括号/引号会自动包裹选区；可在记事本设置中开关**
- **新增：行操作快捷键**：
  - `Ctrl+Shift+K`：删除当前行
  - `Alt+↑`：上移当前行
  - `Alt+↓`：下移当前行
  - `Ctrl+Shift+D`：复制当前行到下一行
  - 以上操作在菜单栏「编辑 → 行操作」子菜单中也可访问
- **新增：大小写转换**：
  - `Ctrl+Shift+U`：循环切换选中文本的大小写（全大写 → 全小写 → 全大写）
  - 右键菜单新增「大小写转换」子菜单，支持：转为大写、转为小写、首字母大写、切换大小写
  - 菜单栏「编辑 → 大小写转换」子菜单中也可访问
- **新增：转到行功能**：`Ctrl+G` 弹出对话框，输入行号后快速跳转到指定行；菜单栏「编辑 → 转到行...」也可访问
- **新增：JSON/XML格式化**：当打开 JSON 或 XML/HTML 文件时，右键菜单显示「格式化文档」选项，一键美化缩进；JSON格式化后缩进为4空格，XML格式化后缩进为2空格

### v1.5.5

- **修复：显示行号开关生效**：记事本设置中的「显示行号」开关现在可以正确控制行号显示/隐藏，修改后即时生效
- **修复：高亮当前行开关生效**：记事本设置中的「高亮当前行」开关现在可以正确控制当前行高亮，修改后即时生效
- **修复：字体大小设置生效**：记事本设置中修改字体大小后立即应用到所有已打开的编辑器（此前仅「视图→缩放」有效）
- **新增：自定义字体选择**：记事本设置中新增字体选择下拉框（QFontComboBox），可从本地字体库中选择任意字体，确认后即时应用
- **文案修改**：「自动缩略图（仅代码文件）」更名为「自动开关缩略图」，含义更清晰

### v1.5.4

- **增强型查找替换**：支持正则表达式、大小写敏感、全词匹配，实时显示「第 N/M 个匹配」计数
- **标签页拖拽移动文件**：将标签拖到文件树的文件夹上即可移动文件
- **Markdown 本地图片支持**：预览中自动解析相对路径图片（如 `![](./img.png)`）
- **记事本设置对话框**：统一管理显示、缩略图、编辑器等选项，「自动缩略图（仅代码文件）」选项移入其中
- **修复缩略图切换卡死 Bug**：`Ctrl+M` 切换缩略图时程序卡死的严重问题已修复

### v1.5.3

- 文件树最小宽度调整至约100px并保留拖拽完全折叠功能
- 修复编辑器首次显示时行号区与文本重叠导致左侧文字被遮挡的问题
- 文件树与编辑区的分割比例现在会自动保存和恢复

### v1.5.2

- 预览代码高亮：Markdown预览中的代码块自动语法着色（Pygments内联样式），配色与左侧编辑器完全一致
- 代码块样式升级：浅蓝色背景（`#EDF3FA`）+ 蓝色左边框（`#4A86C8`），仿PyCharm风格
- 代码块一键复制：代码块左上角📋按钮，点击即复制原始代码到系统剪贴板
- 高亮主题系统：新增 `highlight_themes.py`，统一管理编辑器和预览的配色方案，可通过 `settings.json` 切换主题
- 修复代码块尾部空行：去除 `fenced_code` 扩展在代码块末尾附加的多余换行

### v1.5.1

- 代码缩略图（Minimap）：编辑器右侧鸟瞰图，彩色像素块呈现语法高亮，点击/拖拽快速导航
- 语法高亮配色更新：从VS Code风格切换为PyCharm IntelliJ Light风格（字符串绿色、注释灰色斜体、关键字深蓝加粗）
- Markdown预览改进：预览面板改为PyCharm风格（深色标题、浅灰代码块），去除`nl2br`/`codehilite`扩展以修正排版问题
- Markdown编辑器高亮增强：支持跨行代码块状态追踪（代码块内等宽字体+浅灰背景），标题分级显示

### v1.5

- 语法高亮：基于Pygments，支持30+编程语言
- Markdown分屏预览：左侧编辑，右侧实时渲染
- 自动缩进：智能缩进，Tab插入4空格
- 行宽模式切换：不换行 / 限制行宽
- 修复zip打包中文文件名乱码

### v1.4.1

- 资源平衡调整（前三项均衡，铝材3:1）
- 立绘架构重构（角色/皮肤/状态）
- 修复立绘路径从程序目录读取

### v1.4

- 小秘书定位修复、气泡增大
- 文件夹展开符号修复
- 配置路径持久化
- 编码保持与另存为编码选择

### v1.2

- 挂机机制（在线/离线资源获取）
- 编码检测（UTF-8→GBK→UTF-16）

### v1.0

- 基础记事本功能、游戏框架、小秘书系统
