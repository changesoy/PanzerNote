# PanzerNote 插件 API 技术文档

## 概述

PanzerNote 插件系统提供了一套标准化的扩展机制，允许第三方开发者为应用添加功能。插件运行在沙箱环境中，通过受限 API 与主程序交互。

## 插件生命周期

插件有四个核心生命周期阶段：

| 阶段 | 方法              | 状态          | 说明                            |
| ---- | ----------------- | ------------- | ------------------------------- |
| 加载 | `on_load(api)`    | `LOADED`      | 插件被加载到内存，接收 API 对象 |
| 激活 | `on_activate()`   | `ACTIVATED`   | 插件开始运行，可执行业务逻辑    |
| 停用 | `on_deactivate()` | `DEACTIVATED` | 插件暂停运行，释放运行时资源    |
| 卸载 | `on_unload()`     | `UNLOADED`    | 插件从内存中移除，释放所有资源  |

### 状态转换规则

```
UNLOADED → on_load() → LOADED → on_activate() → ACTIVATED
ACTIVATED → on_deactivate() → DEACTIVATED → on_activate() → ACTIVATED
ACTIVATED → on_deactivate() → DEACTIVATED → on_unload() → UNLOADED
LOADED → on_unload() → UNLOADED
任意状态 → 异常 → ERROR
```

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
  "min_app_version": "X.Y.Z",
  "permissions": ["read_settings", "read_savegame"],
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
- `permissions` (string[]): 权限声明列表
- `tags` (string[]): 标签列表

### 3. 编写入口模块

入口模块必须定义 `Plugin` 类，继承 `PluginBase`：

```python
from src.plugins.plugin_base import PluginBase, PluginMeta, PluginPermission

class Plugin(PluginBase):
    def get_meta(self) -> PluginMeta:
        return PluginMeta(
            name="my_plugin",
            version="1.0.0",
            description="我的自定义插件",
            permissions=[PluginPermission.READ_SETTINGS],
        )

    def on_load(self, api) -> None:
        super().on_load(api)
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

## 权限系统

### 权限分类

| 权限         | 标识                | 说明                             | MVP 可用    |
| ------------ | ------------------- | -------------------------------- | ----------- |
| 读取设置     | `read_settings`     | 读取编辑器、游戏、小秘书等设置   | ✅          |
| 读取存档     | `read_savegame`     | 读取游戏存档数据（资源、核心等） | ✅          |
| 读取工作区   | `read_workspace`    | 读取工作区状态（最近文件等）     | ✅          |
| 读取文件树   | `read_file_tree`    | 读取笔记库目录结构               | ✅          |
| 访问编辑器   | `access_editor`     | 与编辑器交互                     | ✅          |
| 访问 UI      | `access_ui`         | 扩展界面元素                     | ✅          |
| 访问网络     | `access_network`    | 网络请求权限                     | ❌ MVP 禁止 |
| 访问文件系统 | `access_filesystem` | 文件系统写入权限                 | ❌ MVP 禁止 |

### 权限申请格式

在 `plugin.json` 的 `permissions` 数组中声明：

```json
{
  "permissions": ["read_settings", "read_savegame", "access_ui"]
}
```

### MVP 限制

当前 MVP 阶段遵循"先收紧再放开"策略：

- 所有插件仅限只读访问
- `access_network` 和 `access_filesystem` 权限被禁止
- 未声明权限的 API 调用将抛出 `SandboxViolationError`

## 沙箱隔离

### 资源访问控制

- 插件通过 `PluginAPI` 对象访问主程序数据
- 每次调用都检查权限声明
- 未授权访问抛出 `SandboxViolationError`

### API 调用限制

- 插件运行在独立线程中
- 最大执行超时时间：30 秒
- 超时后抛出 `SandboxTimeoutError`

### 异常隔离

- 插件异常不会影响主进程
- 插件进入 `ERROR` 状态后可被重新加载
- 沙箱捕获所有插件异常并记录日志

## PluginAPI 接口参考

### 读取设置

```python
api.get_setting(key, default=None) -> Any
api.get_editor_setting(key, default=None) -> Any
api.get_game_setting(key, default=None) -> Any
api.get_secretary_setting(key, default=None) -> Any
```

**所需权限：** `read_settings`

### 读取存档

```python
api.get_resources() -> Dict[str, int]
api.get_savegame_field(key, default=None) -> Any
```

**所需权限：** `read_savegame`

### 读取工作区

```python
api.get_recent_files() -> List[str]
```

**所需权限：** `read_workspace`

### 读取文件树

```python
api.get_notebooks_path() -> str
```

**所需权限：** `read_file_tree`

### 应用信息

```python
api.get_app_version() -> str
```

**所需权限：** 无

## 热加载

插件管理器支持热加载，可在不重启主程序的情况下更新插件：

```python
manager.reload_plugin("my_plugin")
```

热加载流程：

1. 停用并卸载当前插件
2. 清除模块缓存
3. 重新加载插件模块
4. 恢复之前的激活状态

## 示例插件

### 基础功能插件 (hello_panzer)

展示插件生命周期和只读 API 使用：

```python
class Plugin(PluginBase):
    def get_meta(self) -> PluginMeta:
        return PluginMeta(
            name="hello_panzer",
            version="1.0.0",
            description="基础功能示例插件",
            permissions=[PluginPermission.READ_SETTINGS, PluginPermission.READ_SAVEGAME],
        )

    def on_activate(self) -> None:
        super().on_activate()
        if self._api:
            resources = self._api.get_resources()
            print(f"当前资源: {resources}")
```

### UI 扩展插件 (word_counter)

展示 UI 扩展和编辑器交互：

```python
class Plugin(PluginBase):
    def get_meta(self) -> PluginMeta:
        return PluginMeta(
            name="word_counter",
            version="1.0.0",
            description="文档字数统计",
            permissions=[
                PluginPermission.READ_SETTINGS,
                PluginPermission.ACCESS_EDITOR,
                PluginPermission.ACCESS_UI,
            ],
        )

    def count_text(self, text: str) -> dict:
        return {
            "words": len(text.split()),
            "chars": len(text),
            "lines": len(text.split('\n')),
        }
```

## 错误处理

| 异常类型                | 说明             |
| ----------------------- | ---------------- |
| `PluginLoadError`       | 插件加载失败     |
| `PluginValidationError` | 插件清单验证失败 |
| `SandboxViolationError` | 权限违规         |
| `SandboxTimeoutError`   | 执行超时         |
