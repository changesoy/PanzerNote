# PanzerNote 未来规划与技术设计备忘录

## 1. 总体判断

PanzerNote 当前和未来一段时间内都不需要急着采用混合编程，也不需要为了性能、美观或游戏侧系统提前重写技术栈。

项目的主体仍然适合继续使用：

```text
Python + PyQt6 / Qt
```

未来即使加入建造、图鉴、装备、技能、全文搜索、插件系统等功能，主要复杂度也不会来自 Python 性能不足，而是来自：

```text
架构分层
模块边界
数据组织
UI 组件化
存档兼容
资源管理
插件安全边界
```

因此，短中期最重要的不是更换语言，而是把现有结构重构清楚，避免大文件继续膨胀，避免 UI、业务逻辑、存储逻辑混在一起。

---

## 2. 混合编程策略

### 2.1 短期不采用混合编程

短期内不需要使用 Rust、C++、C# 或其他语言重写主流程、UI 或游戏系统。

之前尝试用 Rust 重写启动主流程后发现没有明显加速，这是合理的，因为 PanzerNote 的启动瓶颈大概率不在 `main.py` 的流程控制，而是在：

```text
Python 解释器启动
PyQt6 导入
Qt 初始化
QApplication 创建
主窗口构建
QtWebEngine / Markdown 预览初始化
主题、图标、字体加载
插件扫描
会话恢复
```

重写启动胶水层并不能显著减少这些成本。

### 2.2 Rust / C++ 的适用场景

未来只有在下面两类情况出现时，才考虑混合编程：

```text
1. 大规模全文索引 / 模糊搜索 / 本地数据库查询非常重
2. 强沙箱 / 进程管理 / Windows 权限控制
```

其中第二类更可能需要 native helper。

推荐做法不是重写整个项目，而是只写一个很小的 native launcher/helper：

```text
panzernote_sandbox_launcher.exe
```

它只负责：

```text
启动受限插件进程
设置 Job Object
设置 Restricted Token
设置 AppContainer
管理进程树
强制终止插件进程
```

主程序、UI、编辑器、游戏系统、插件协议仍然继续使用 Python。

### 2.3 C++ 与 Rust 的取舍

如果未来只是写 Windows sandbox launcher，C++ 对当前项目可能比 Rust 更合适，因为：

```text
Win32 示例更多
和 Windows API 贴合更自然
AI 辅助生成和修改时更容易对照文档
不需要处理 Rust 的所有权、生命周期、借用检查
```

但如果不是为了沙箱和进程权限控制，就没有必要为了“可能更快”而引入 C++。

### 2.4 不建议 C# 混合 UI

不建议为了显示美观而把 C# / WPF / WinUI 混进现有 PyQt 项目。

原因是：

```text
会引入两个 UI 框架
两个运行时
两个事件循环
打包复杂度上升
状态同步变复杂
调试链路变长
主题风格可能不一致
```

如果未来想让游戏侧 UI 更精美，优先考虑 Qt 生态内的方案：

```text
PyQt Widgets 继续优化
必要时局部引入 QML / Qt Quick
```

而不是 C#。

---

## 3. 启动速度优化路线

为了加速启动，不应优先考虑混合编程，而应优先做 profiling 和懒加载。

推荐方向：

```text
使用 python -X importtime 分析 import 耗时
延迟导入 PyQt6.QtWebEngineWidgets
延迟导入 markdown / pygments / PIL / cryptography 等重模块
主窗口先显示，再加载重组件
插件启动时只读取 plugin.json，不 import 插件代码
Markdown 预览首次使用时再创建
Minimap / 文件树 / 小秘书 / 图鉴等模块按需加载
会话恢复分阶段进行，只立即加载当前标签
```

目标不是单纯追求总启动时间最短，而是提升用户体感：

```text
窗口尽快出现
核心编辑器尽快可用
重功能后台或按需加载
```

---

## 4. 插件系统远期规划

### 4.1 当前定位

当前阶段插件系统可以继续定位为可信插件模型。

也就是说：

```text
插件和普通 Python 包类似
安装插件意味着信任插件作者
插件不应被描述成强沙箱环境
```

文档中应明确提示：

```text
Legacy / Trusted 插件运行在 PanzerNote 主进程中
拥有与当前用户相同的本地权限
请只安装可信来源插件
```

### 4.2 中期重构方向：Capability API

即使暂时不做强沙箱，也应逐步把插件 API 改成能力接口，而不是把主程序对象直接暴露给插件。

不建议插件直接拿到：

```text
MainWindow
EditorTabs
ConfigManager
SaveGameManager
真实 Qt Widget 对象
```

建议改为：

```python
class PluginContext:
    def register_command(self, command_id: str, title: str): ...
    def get_current_document_text(self) -> str: ...
    def replace_selection(self, text: str): ...
    def show_notification(self, text: str): ...
    def read_plugin_data(self, key: str): ...
    def write_plugin_data(self, key: str, value): ...
```

这样可以减少误用，也为未来独立进程插件打基础。

### 4.3 远期强沙箱方向

未来如果要做强沙箱，不要试图在 CPython 主进程内部限制插件，而是改成：

```text
PanzerNote 主进程 / Broker
  ↕ IPC / JSON-RPC
Sandboxed Plugin Host 进程
  ↕
插件代码
```

推荐结构：

```text
PanzerNote 主进程
  ├─ PluginBroker
  │   ├─ PermissionChecker
  │   ├─ JsonRpcRouter
  │   ├─ PluginProcessManager
  │   └─ CapabilityDispatcher
  │
  └─ plugin_host.py 子进程
      └─ 插件 main.py
```

插件进程不直接操作主窗口、真实文件、真实存档，只能通过 Broker 请求能力。

### 4.4 IPC 协议

IPC 不应使用 `pickle`。

推荐使用：

```text
length-prefixed JSON
JSON-RPC 风格协议
Windows Named Pipe
stdin/stdout 管道
```

示例：

```json
{
  "id": "req-001",
  "method": "editor.getCurrentText",
  "params": {}
}
```

Broker 收到请求后执行：

```text
校验 schema
检查权限
调用受控服务
返回结果
```

### 4.5 进程强杀与 Windows 权限控制

如果只想解决插件卡死，独立子进程即可。

如果想杀干净插件及其子进程，需要 Windows Job Object。

如果想做更强的隔离，未来可以逐步考虑：

```text
Job Object
Restricted Token
Low Integrity
AppContainer
```

最终理想结构：

```text
PanzerNote.exe / main.py
  └─ panzernote_sandbox_launcher.exe
      └─ AppContainer + Job Object + Restricted Token
          └─ python.exe plugin_host.py
              └─ plugin main.py
```

这部分可以作为未来唯一比较合理的混合编程场景。

---

## 5. 是否需要前后端分离

### 5.1 不建议传统前后端分离

PanzerNote 是本地桌面应用，不是 Web 服务，也不是多人在线应用。

因此不建议做传统意义上的：

```text
前端 UI 进程
  ↕ HTTP / WebSocket
后端服务进程
  ↕
数据库服务
```

这样会带来：

```text
多进程管理
协议设计
状态同步
打包复杂
启动更慢
调试困难
本地安全边界更复杂
```

### 5.2 推荐内部层次分离

更适合 PanzerNote 的是本地单体应用内部的清晰分层：

```text
UI 层
  ↓
Application Service 应用服务层
  ↓
Domain Model 领域逻辑层
  ↓
Repository / Storage 存储层
  ↓
JSON + SQLite + 文件资源
```

推荐目录结构：

```text
src/
  app/
    app_context.py
    event_bus.py
    service_registry.py

  ui/
    main_window.py
    editor/
    game/
    settings/
    shared/

  domain/
    document/
    game/
    plugin/

  services/
    document_service.py
    search_service.py
    construction_service.py
    collection_service.py
    resource_service.py
    plugin_service.py

  storage/
    sqlite/
      connection.py
      migrations.py
      repositories.py
    json/
      config_store.py
      content_loader.py

  workers/
    search_index_worker.py
    file_scan_worker.py
    plugin_host_manager.py
```

核心原则：

```text
UI 不直接读写数据库
UI 不直接修改 savegame
UI 不直接 import 插件
Service 负责业务流程
Repository 负责存储
Worker 负责慢任务
Domain 保持纯逻辑
```

---

## 6. 数据存储规划

### 6.1 当前阶段

当前可以继续使用 JSON 和普通文件。

适合继续用 JSON 的内容：

```text
settings.json
workspace.json
theme.json
plugin.json
ships.json
equipment.json
skills.json
recipes.json
```

这些内容配置性强、可手工编辑、数据量不大，用 JSON 比数据库更合适。

### 6.2 中期引入 SQLite

中期建议引入 SQLite，但不建议引入 MySQL。

SQLite 适合：

```text
单用户
本地应用
离线使用
无需单独数据库服务
打包简单
事务可靠
查询方便
```

MySQL 对 PanzerNote 来说过重，除非未来要做多端同步、多人共享或服务器版本。

### 6.3 SQLite 适合存什么

适合放 SQLite 的内容：

```text
全文搜索索引
文件元数据缓存
最近打开记录
文档 hash / mtime / size
图鉴获得状态
建造历史
资源变动流水
成就状态
插件数据
装备库存
每日签到记录
```

不建议把真实笔记正文全部塞进数据库。

真实笔记文件应该继续保持为：

```text
.md
.txt
普通文件
```

这样用户可以用其他编辑器打开，也不会因为数据库损坏导致所有笔记不可读。

### 6.4 推荐存储结构

推荐结构：

```text
PanzerNoteData/
  config/
    settings.json
    workspace.json

  game_data/
    ships.json
    equipment.json
    skills.json
    recipes.json

  saves/
    savegame.json 或 panzernote.db

  index/
    search_index.db

  assets/
    characters/

  plugins/
    plugin_data/
```

或者中后期合并为：

```text
panzernote.db
  documents
  document_fts
  document_meta
  collection
  construction_history
  resource_events
  achievements
  plugin_kv
```

---

## 7. 全文搜索与模糊搜索规划

### 7.1 全文搜索

远期可以使用 SQLite FTS5 做全文搜索索引。

基本流程：

```text
DocumentRepository
  - 负责读写真实文件

SearchIndexService
  - 监听文件变化
  - 提取文本
  - 计算 hash
  - 更新 FTS 索引

SearchRepository
  - 查询 SQLite FTS5
  - 返回文件路径、片段、rank
```

概念表：

```sql
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    title TEXT,
    mtime REAL,
    size INTEGER,
    content_hash TEXT
);

CREATE VIRTUAL TABLE document_fts USING fts5(
    title,
    content,
    content='',
    tokenize='unicode61'
);
```

中文搜索可以先做够用版本：

```text
英文 / 数字：FTS5
中文：LIKE fallback 或简单 n-gram
```

远期如果中文搜索体验不够，再考虑专门分词或搜索库。

### 7.2 模糊搜索

命令面板、文件名、角色名、装备名、图鉴筛选等模糊搜索，不需要 native 模块。

Python 内存搜索就足够：

```text
几百个命令
几千个文件
几百个角色
几百件装备
```

如果未来正文模糊搜索很重，可以采用两阶段方案：

```text
先用 SQLite FTS5 找候选
再用 Python fuzzy scorer 对前 100 条排序
```

只有在数据规模真的巨大时，才考虑 native 搜索模块。

---

## 8. 游戏侧系统规划

### 8.1 游戏侧不需要混合编程

建造、图鉴、装备、技能这些系统本质是低频、数据驱动、事件驱动的桌面功能。

它们主要操作是：

```text
读取角色数据
计算建造概率
消耗资源
生成结果
更新图鉴状态
保存玩家状态
展示角色 / 装备 / 技能信息
```

这些对 Python 来说没有性能压力。

真正需要注意的是：

```text
数据表设计
存档版本兼容
UI 与逻辑解耦
概率公式可测试
资源循环平衡
角色图鉴状态管理
装备和技能扩展性
```

### 8.2 游戏系统优先级

推荐优先级：

```text
第一优先级：
建造系统 + 图鉴系统 + 角色详情页

第二优先级：
资源消耗循环 + 每日签到 + 成就 / 收集奖励

第三优先级：
装备系统

第四优先级：
技能系统

最后才考虑：
战斗、编队、远征、复杂数值系统
```

装备和技能如果没有战斗、远征、任务或编队收益，容易变成摆设，因此不要太早投入过多精力。

### 8.3 游戏侧推荐结构

```text
src/game/
  data/
    ships.json
    equipment.json
    recipes.json
    skills.json

  models/
    ship.py
    equipment.py
    skill.py
    construction.py
    player_state.py

  services/
    construction_service.py
    collection_service.py
    equipment_service.py
    skill_service.py
    resource_service.py

  ui/
    construction_panel.py
    collection_panel.py
    ship_detail_panel.py
    equipment_panel.py
```

核心原则：

```text
游戏逻辑不要写在 PyQt widget 里
UI 只负责显示和发出操作请求
Service 负责具体业务
Repository 负责读写状态
```

建造流程示例：

```text
ConstructionPanel
  -> ConstructionService.start_build(recipe)
  -> ResourceService.consume(...)
  -> ConstructionRepository.create_order(...)
  -> EventBus.emit("construction.started")
  -> UI 更新资源和建造队列
```

---

## 9. 游戏 UI 与美术表现

### 9.1 PyQt Widgets 足够支撑初期游戏侧

初期建造页可以是：

```text
资源输入区
建造按钮
建造队列
结果弹窗
历史记录
```

图鉴页可以是：

```text
左侧筛选
中间角色卡片网格
右侧详情面板
```

这些 PyQt Widgets 足够完成。

### 9.2 中后期可以局部使用 QML / Qt Quick

如果未来想做更强的游戏感，可以在局部游戏面板里尝试 QML：

```text
建造完成动画
角色获得演出
稀有度闪光
卡片翻转
资源条动态变化
小秘书面板
```

不需要把整个应用迁移到 QML，也不需要引入 C#。

推荐路线：

```text
主编辑器 / 文件树 / 设置页：
  PyQt Widgets

游戏侧展示面板：
  PyQt Widgets 起步
  需要更强视觉表现时局部 QML
```

---

## 10. 角色立绘与资产系统

### 10.1 基本原则

角色立绘应该作为独立资产系统管理，而不是简单丢进 `assets/`。

核心边界：

```text
立绘文件是资产
角色状态是数据
显示方式是 UI
```

三者不要混在一起。

### 10.2 版权策略

如果项目会开源、发布安装包、上传截图或演示视频，就不要把版权不明的手游立绘直接打进仓库或发布包。

推荐三档处理：

```text
仓库内置：
  只放原创、明确授权、CC0 或允许使用的素材

用户本地导入：
  用户自己把图片放进 assets_local/，项目不随包分发

开发占位图：
  使用 silhouette / placeholder / 色块卡片
```

### 10.3 文件格式

推荐：

```text
普通立绘：PNG / WebP
大破立绘：PNG / WebP
缩略图：WebP / JPEG
头像：PNG / WebP
UI 图标：SVG / PNG
占位图：SVG / PNG
```

立绘不要放进 SQLite，数据库只存路径、hash、版本和解锁状态。

### 10.4 推荐目录结构

```text
assets/
  characters/
    pn_001/
      normal.png
      damaged.png
      thumb.webp
      silhouette.png
      meta.json

    pn_002/
      normal.png
      thumb.webp
      silhouette.png
      meta.json

data/
  characters.json
```

角色数据示例：

```json
{
  "id": "pn_001",
  "name": "角色名",
  "rarity": 5,
  "type": "destroyer",
  "artist": "your_name",
  "asset": {
    "base_dir": "assets/characters/pn_001",
    "normal": "normal.png",
    "damaged": "damaged.png",
    "thumb": "thumb.webp",
    "silhouette": "silhouette.png"
  },
  "license": {
    "type": "original",
    "author": "your_name",
    "source": null
  }
}
```

### 10.5 AssetManager

建议实现统一的 `AssetManager`。

```text
src/assets/
  asset_manager.py
  image_cache.py
  character_assets.py
```

职责：

```text
根据 character_id 找图片路径
检查资源是否存在
缺失时返回 placeholder
加载 QPixmap
生成缩略图缓存
处理高 DPI
记录资源 hash / version
支持未来资源包
```

UI 不应该自己拼路径：

```python
# 不推荐
QPixmap(f"assets/characters/{ship_id}/normal.png")

# 推荐
pixmap = asset_manager.get_character_pixmap(ship_id, "normal")
```

### 10.6 加载策略

不要启动时加载所有大图。

推荐：

```text
启动时：
  只读取角色 metadata

打开图鉴：
  只加载可见区域缩略图

进入角色详情：
  才加载 normal 立绘

切换皮肤 / 大破：
  按需加载

建造结果：
  只加载当前结果立绘
```

中期可以做：

```text
缩略图缓存
QPixmap LRU cache
资源缺失检查器
资源包 manifest
```

### 10.7 暂不考虑差分表情和 Live2D

由于不打算约稿或投入大量美术资源，暂不考虑：

```text
差分表情
Live2D
Spine
复杂骨骼动画
```

未来最多考虑：

```text
静态 PNG / WebP
简单淡入
轻微缩放
稀有度闪光
卡片翻转
QML 局部动画
```

---

## 11. 近期最应该做的事情

短期优先级：

```text
1. 继续完善记事本主体功能
2. 重构现有大文件
3. 拆分 UI / Service / Storage / Domain
4. 统一 ThemeManager / StyleManager
5. 优化启动：profiling、懒加载、分阶段初始化
6. 插件系统文档明确可信模型
7. 插件 API 逐步改成 Capability API
8. 游戏侧先做数据驱动结构，不急着做复杂玩法
```

短期不做：

```text
混合编程
C# UI
Rust / C++ 重写主流程
传统前后端分离
MySQL
Live2D
复杂战斗系统
```

---

## 12. 中期路线图

中期可以推进：

```text
SQLite 引入
全文搜索索引
图鉴系统 MVP
建造系统 MVP
角色详情页
资源消耗循环
成就 / 收集奖励
AssetManager
角色立绘资源管理
插件 manifest 权限声明
后台 worker 处理慢任务
```

中期架构目标：

```text
项目仍然是本地单体应用
但内部层次清晰
数据与 UI 解耦
游戏逻辑可测试
存储层可替换
插件系统为未来独立进程预留接口
```

---

## 13. 远期路线图

远期再考虑：

```text
SQLite FTS5 全文搜索增强
中文搜索优化
搜索索引 worker
插件独立 plugin_host.py
JSON-RPC IPC
Windows Job Object
Restricted Token
AppContainer
native sandbox launcher
局部 QML 游戏面板
装备系统
技能系统
更复杂的图鉴筛选
资源包系统
```

只有出现明确性能瓶颈或安全需求时，才引入 native 模块。

---

## 14. 最终技术路线总结

PanzerNote 最适合的路线不是“重写”或“前后端分离”，而是：

```text
本地单体应用
  +
清晰内部架构分层
  +
JSON 静态配置
  +
SQLite 本地持久层
  +
普通文件保存真实笔记
  +
按需 Worker
  +
未来可选插件沙箱进程
```

推荐长期方向：

```text
Python 继续负责：
  UI
  编辑器
  游戏系统
  插件 API
  业务逻辑
  存储组织
  数据驱动内容

SQLite 负责：
  搜索索引
  历史记录
  图鉴状态
  资源流水
  成就
  插件数据

QML 可选负责：
  游戏侧更精美的局部 UI

C++ 可选负责：
  沙箱启动器
  Windows Job Object
  AppContainer
  Restricted Token
  插件进程管理
```

最重要的原则：

```text
不要提前支付复杂度成本。
先把结构边界立清楚。
只有在真实瓶颈出现时，再引入更重的技术。
```

当前阶段最应该投资的是：

```text
重构
分层
数据驱动
懒加载
资产管理
存档兼容
可测试的游戏服务
```

这些做好后，未来无论是继续做记事本、加入建造图鉴、扩展搜索，还是实现插件沙箱，都会顺很多。
