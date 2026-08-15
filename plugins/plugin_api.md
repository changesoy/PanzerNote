# PanzerNote 插件 API 技术文档

## 概述

PanzerNote 插件系统提供了一套标准化的扩展机制，允许第三方开发者为应用添加功能。插件通过**能力声明（capabilities）** 与宿主交互：插件在 `plugin.json` 中声明所需能力，宿主按能力清单暴露受限 API。

> **⚠️ 可信插件模型**：插件运行在主程序进程中（GUI 线程），不是安全沙箱。能力系统只限制 PanzerNote 暴露的 API 边界，无法阻止恶意插件读取进程内其它数据。请只安装可信来源的插件。

## 插件生命周期

插件有四个核心生命周期阶段：

| 阶段 | 方法              | 状态          | 说明                              |
| ---- | ----------------- | ------------- | --------------------------------- |
| 加载 | `on_load(ctx)`    | `LOADED`      | 插件被加载到内存，接收上下文对象  |
| 激活 | `on_activate()`   | `ACTIVATED`   | 插件开始运行，可执行业务逻辑      |
| 停用 | `on_deactivate()` | `DEACTIVATED` | 插件暂停运行，释放运行时资源      |
| 卸载 | `on_unload()`     | `UNLOADED`    | 插件从内存中移除，释放所有资源    |

### 状态转换规则

```
UNLOADED → on_load() → LOADED → on_activate() → ACTIVATED
ACTIVATED → on_deactivate() → DEACTIVATED → on_activate() → ACTIVATED
ACTIVATED → on_deactivate() → DEACTIVATED → on_unload() → UNLOADED
LOADED → on_unload() → UNLOADED
任意状态 → 异常 → ERROR
```

所有生命周期钩子在 GUI 线程执行；插件应避免在钩子中执行长时间阻塞操作。

## 插件开发指南

### 1. 创建插件包

插件以目录形式组织，包含 `plugin.json` 清单文件和 Python 入口模块：

```
plugins/
└── my_plugin/
    ├── plugin.json    # 插件清单（必需）
    └── main.py        # 入口模块（必需）
```

### 2. 编写 plugin.json

```json
{
  "name": "my_plugin",
  "version": "1.0.0",
  "description": "我的自定义插件",
  "author": "开发者名称",
  "entry": "main.py",
  "min_app_version": "1.9.0",
  "capabilities": ["settings.read", "savegame.read"],
  "tags": ["utility"]
}
```

**必需字段：**

- `name` (string): 插件唯一标识符，仅允许字母、数字和下划线
- `version` (string): 语义化版本号
- `entry` (string): 入口模块文件名

**可选字段：**

- `description` (string): 插件描述
- `author` (string): 作者名称
- `homepage` (string): 项目主页 URL
- `min_app_version` (string): 最低兼容应用版本，默认为当前应用版本（通过 `src.__version__` 获取）
- `capabilities` (string[]): **能力声明列表**，决定插件可调用的 API
- `tags` (string[]): 标签列表

> 能力声明只需列出实际用到的能力。`data.read` / `data.write` 为内置能力，无需声明。

### 3. 编写入口模块

入口模块必须定义 `Plugin` 类，继承 `PluginBase`：

```python
from src.plugins.plugin_base import PluginBase, PluginMeta

class Plugin(PluginBase):
    def get_meta(self) -> PluginMeta:
        return PluginMeta(
            name="my_plugin",
            version="1.0.0",
            description="我的自定义插件",
            capabilities=["settings.read"],
        )

    def on_load(self, ctx) -> None:
        super().on_load(ctx)
        # 保存 ctx 供后续使用（self._ctx 已在基类中保存）
        # 初始化插件资源

    def on_activate(self) -> None:
        super().on_activate()
        # 启动插件功能

    def on_deactivate(self) -> None:
        super().on_deactivate()
        # 暂停插件功能

    def on_unload(self) -> None:
        # 释放所有资源
        super().on_unload()
```

## 能力系统

### 两层结构

能力系统采用"声明 → 映射"两层结构：

1. **manifest 声明**：插件在 `plugin.json` 的 `capabilities` 中声明所需能力（如 `"editor.read_text"`）
2. **权限映射**：宿主将能力 id 映射为内部权限枚举（`PluginPermission`），未声明的能力无法调用

### 能力清单

| 能力 id                    | 内部权限            | 说明                                     |
| -------------------------- | ------------------- | ---------------------------------------- |
| `app.version`              | 无                  | 获取应用版本                             |
| `settings.read`            | `READ_SETTINGS`     | 读取设置                                 |
| `savegame.read`            | `READ_SAVEGAME`     | 读取游戏存档（资源、字段）               |
| `workspace.recent_files`   | `READ_WORKSPACE`    | 读取最近文件列表                         |
| `workspace.open_file`      | `OPEN_FILE`         | 打开文件到编辑器                         |
| `file_tree.read`           | `READ_FILE_TREE`    | 读取笔记库路径                           |
| `editor.read_text`         | `EDITOR_READ`       | 读取当前文档全文                         |
| `editor.read_path`         | `EDITOR_READ`       | 读取当前文件路径                         |
| `editor.selection.read`    | `EDITOR_READ`       | 读取当前选区文本                         |
| `editor.selection.replace` | `EDITOR_WRITE`      | 替换当前选区                             |
| `ui.notify`                | `UI_NOTIFY`         | 状态栏轻提示                             |
| `ui.show_message`          | `SHOW_MESSAGE`      | 通过小秘书显示消息                       |
| `ui.register_command`      | `REGISTER_COMMAND`  | 注册命令面板命令                         |
| `ui.register_menu_item`    | `REGISTER_MENU`     | 注册插件菜单项                           |
| `event.subscribe`          | `EVENT_SUBSCRIBE`   | 订阅宿主事件                             |
| `data.read` / `data.write` | 内置（无需声明）    | 读写插件私有数据（`plugin_data/{id}/`）  |

### 权限不足的行为

- 调用**未声明**或**不存在**的能力 → 抛出 `PluginCapabilityError`
- 能力存在但内部权限换算不通过（宿主内部不一致）→ 抛出 `PluginPermissionError`

## PluginContext 接口参考

`on_load(ctx)` 接收的 `ctx` 是命名空间式上下文对象。插件**不直接持有** Config / SavegameManager / MainWindow 等内部对象，只通过命名空间方法访问能力。每次调用都会经过权限检查，返回值做深拷贝保护。

### ctx.app — 应用信息

| 方法             | 所需能力      | 说明             |
| ---------------- | ------------- | ---------------- |
| `version() -> str` | `app.version` | 获取应用版本     |

### ctx.settings — 设置读取

| 方法                                  | 所需能力      | 说明                     |
| ------------------------------------- | ------------- | ------------------------ |
| `get(key, default=None) -> Any`       | `settings.read` | 读取通用设置           |
| `get_editor(key, default=None) -> Any` | `settings.read` | 读取编辑器设置         |
| `get_game(key, default=None) -> Any`   | `settings.read` | 读取游戏设置           |
| `get_secretary(key, default=None) -> Any` | `settings.read` | 读取小秘书设置       |

### ctx.savegame — 存档读取

| 方法                            | 所需能力      | 说明                   |
| ------------------------------- | ------------- | ---------------------- |
| `resources() -> Dict[str, int]` | `savegame.read` | 读取游戏资源         |
| `field(key, default=None) -> Any` | `savegame.read` | 读取存档字段         |

### ctx.workspace — 工作区

| 方法                          | 所需能力               | 说明                 |
| ----------------------------- | ---------------------- | -------------------- |
| `recent_files() -> List[str]` | `workspace.recent_files` | 读取最近文件列表   |
| `open_file(filepath) -> bool` | `workspace.open_file`   | 打开文件到编辑器（经宿主安全校验） |

### ctx.file_tree — 笔记库

| 方法                        | 所需能力      | 说明           |
| --------------------------- | ------------- | -------------- |
| `notebooks_path() -> str`   | `file_tree.read` | 读取笔记库路径 |

### ctx.editor — 编辑器

| 方法                            | 所需能力                 | 说明                                     |
| ------------------------------- | ------------------------ | ---------------------------------------- |
| `get_text() -> str`             | `editor.read_text`       | 读取当前文档全文                         |
| `get_current_path() -> Optional[str]` | `editor.read_path` | 获取当前文件路径（未保存的新文件返回 None） |
| `replace_text(text)`            | `editor.selection.replace` | 用给定文本替换当前选区                 |
| `selection.get_text() -> str`   | `editor.selection.read`    | 读取当前选区文本（无选区返回空串）     |

### ctx.ui — UI 扩展

| 方法                                    | 所需能力                 | 说明                                   |
| --------------------------------------- | ------------------------ | -------------------------------------- |
| `notify(message, level="info")`         | `ui.notify`              | 状态栏轻提示（level: info/warning/error） |
| `show_message(message)`                 | `ui.show_message`        | 通过小秘书显示消息                     |
| `register_command(command_id, handler)` | `ui.register_command`    | 注册命令面板命令（id 建议 `插件名:动作`） |
| `register_menu_item(label, handler)`    | `ui.register_menu_item`  | 注册插件菜单项                         |

### ctx.data — 插件私有数据（内置能力）

| 方法                    | 说明                                                                 |
| ----------------------- | -------------------------------------------------------------------- |
| `read(key) -> Any`      | 读取本插件数据，key 不存在返回 None                                  |
| `write(key, value)`     | 写入本插件数据（值需可 JSON 序列化，超过 1MB 拒绝写入）              |

数据存于用户数据目录 `data/plugin_data/{plugin_id}/data.json`（单 JSON 文件），写盘走 `FileGuard.safe_write`（原子写），**仅限本插件命名空间**。卸载插件默认保留数据，需显式操作删除。

### ctx.events — 事件订阅

| 方法                            | 所需能力       | 说明                          |
| ------------------------------- | -------------- | ----------------------------- |
| `subscribe(name, handler)`      | `event.subscribe` | 订阅事件，handler 接收 payload（可为 None） |

**事件白名单（7 个）：**

| 事件名             | 说明                 | 节流     |
| ------------------ | -------------------- | -------- |
| `document.opened`  | 文档打开（带 filepath） | 否     |
| `document.saved`   | 文档保存             | 否       |
| `document.closed`  | 文档关闭（带 filepath） | 否     |
| `cursor.changed`   | 光标移动             | 100ms 合并 |
| `content.changed`  | 内容变更             | 100ms 合并 |
| `theme.changed`    | 主题切换（带主题 id）  | 否     |
| `file_tree.changed`| 文件树变化           | 否       |

防护规则：

- 高频事件（`cursor.changed` / `content.changed`）合并到 100ms 窗口后派发，仅保留最新 payload
- 单插件单事件订阅数上限 5，超限抛出 `PluginCapabilityError`
- 订阅回调异常仅记录日志，不自动禁用插件
- 插件卸载/重载时自动解绑全部订阅

## 主线程模型

- 所有生命周期钩子与命令回调在 **GUI 线程**执行，无独立插件线程
- 无执行超时机制；插件自行将长任务卸载（如异步处理）
- 插件回调应快速返回，避免阻塞界面

## 异常与错误处理

| 异常类型                | 触发时机                                   |
| ----------------------- | ------------------------------------------ |
| `PluginLoadError`       | 插件加载失败（模块导入、类缺失等）         |
| `PluginValidationError` | 插件清单验证失败（必需字段缺失等）         |
| `PluginCapabilityError` | 调用未声明/不存在的能力、事件不在白名单、订阅超限 |
| `PluginPermissionError` | 能力已知但内部授权不满足                   |

异常隔离规则：

- 生命周期钩子异常 → 插件进入 `ERROR` 状态（可重新加载）
- 回调（命令/菜单/事件订阅）异常 → 仅记录日志，插件保持运行

## 热加载

插件管理器支持热加载，可在不重启主程序的情况下更新插件：

```python
manager.reload_plugin("my_plugin")
```

热加载流程：

1. 停用并卸载当前插件（自动解绑事件订阅）
2. 清除模块缓存
3. 重新加载插件模块
4. 恢复之前的激活状态

## 示例插件

### 基础功能插件 (hello_panzer)

展示生命周期和只读命名空间 API 使用：

```python
from src.plugins.plugin_base import PluginBase, PluginMeta
from src import __version__ as _app_version

class Plugin(PluginBase):
    def get_meta(self) -> PluginMeta:
        return PluginMeta(
            name="hello_panzer",
            version="1.0.0",
            description="生命周期 + 只读资源 API 示例插件",
            author="PanzerNote Team",
            min_app_version=_app_version,
            capabilities=["app.version", "settings.read", "savegame.read"],
        )

    def on_load(self, ctx) -> None:
        super().on_load(ctx)
        version = ctx.app.version()
        print(f"[HelloPanzer] 插件已加载 (应用版本: {version})")

    def on_activate(self) -> None:
        super().on_activate()
        if self._ctx:
            resources = self._ctx.savegame.resources()
            print(f"[HelloPanzer] 当前资源: 燃料={resources.get('fuel', 0)}")
```

### UI 扩展插件 (word_counter)

展示编辑器读取能力：

```python
from src.plugins.plugin_base import PluginBase, PluginMeta
from src import __version__ as _app_version

class Plugin(PluginBase):
    def get_meta(self) -> PluginMeta:
        return PluginMeta(
            name="word_counter",
            version="1.0.0",
            description="字数统计能力示例插件",
            author="PanzerNote Team",
            min_app_version=_app_version,
            capabilities=["editor.read_text"],
        )

    def count_text(self, text: str) -> dict:
        if not text:
            return {"words": 0, "chars": 0, "chars_no_spaces": 0, "lines": 0}
        lines = text.split('\n')
        return {
            "words": len(text.split()),
            "chars": len(text),
            "chars_no_spaces": len(text.replace(' ', '').replace('\t', '').replace('\n', '')),
            "lines": len(lines),
        }
```

> 完整示例见 `plugins/hello_panzer/` 与 `plugins/word_counter/`。
