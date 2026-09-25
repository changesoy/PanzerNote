# 启动性能实测报告（1.6）

> 实测日期：2026-09-23｜版本基线：2.5.0｜环境：Windows，Python 3.14.7 + PyQt6 6.11.0，
> 数据目录 `D:/Users/chang/Downloads/PanzerNote`（机械盘/常规 SSD 未区分）。
> 测量方式：`python -X importtime` 采集模块导入耗时；`StartupProfiler`（main.py 各
> `begin_phase/end_phase`）采集阶段耗时。数据目录与日志见文末「测量方法」。

## 1. 阶段耗时（StartupProfiler）

| 轮次 | 配置初始化 | 日志初始化 | 主窗口创建 | 窗口显示 | 总计   | 备注                     |
| ---- | ---------- | ---------- | ---------- | -------- | ------ | ------------------------ |
| 冷启动 | 9167.4ms | 5.8ms      | 1144.2ms   | 19.9ms   | 10337.2ms | 当日首次运行（见 2.3） |
| 热启动 | 14.9ms   | 17.1ms     | 2461.9ms   | 272.5ms  | 2766.3ms  | 进程级缓存已预热        |

- 冷启动的 9.2s「配置初始化」为**一次性异常值**（当日首启；热启动同阶段仅 14.9ms）。
  推断为文件缓存未预热 + 杀毒软件实时扫描所致，**不是代码路径问题**，无需针对性优化，
  但值得在用户文档中说明「首次启动较慢属正常」。
- 热启动的瓶颈明确在**主窗口创建**（2.46s），其中包含 `src.main_window` 模块链导入
  与 MainWindow 构造两部分（见 2.1/2.2）。

## 2. 模块导入耗时（`-X importtime`）

### 2.1 预 main() 导入（main.py 顶层 import，即 import main 的成本）

| 场景 | 总计 | 大头（cum） |
| ---- | ---- | ----------- |
| 冷启动 | ~1744ms | `asyncio` 845ms（→ logging 424ms、traceback 329ms）、`src.ui.first_run_dialog` 253ms（→ themes.bootstrap 241ms，含 dataclasses/inspect/_colorize）、`PyQt6.QtWidgets` 191ms、`src.core.config` 175ms、`shutil` 141ms |
| 热启动 | ~365–406ms | `asyncio` 148ms、`first_run_dialog` 75ms、`PyQt6.QtWidgets` 53ms、`src.core.config` 49ms |

### 2.2 实跑热启动全量导入（含主窗口创建期）

总计 **~1580ms**，root 模块 24 个。主要构成：

| 模块（root）      | cum     | 主要子依赖                                  |
| ----------------- | ------- | ------------------------------------------- |
| `src.main_window` | 1024.4ms | `editor_tabs` 823.8ms → `markdown_preview` 632.4ms → **`markdown_it` 462.8ms**、`markdown` 92.9ms；`editor` 145.5ms |
| `asyncio`         | 206.0ms | （qasync 事件循环必需）                     |
| `src.ui.first_run_dialog` | 76.1ms | `themes.bootstrap` 72.9ms          |
| `PyQt6.QtWidgets` | 62.3ms  | 必需                                        |
| `src.core.config` | 50.9ms  |                                             |
| `shutil`          | 38.6ms  | 仅 crash log 迁移使用                       |

### 2.3 冷启动异常值的边界说明

冷启动样本只取得一轮（GUI 实测受用户会话限制），9.2s 未复测。热启动 14.9ms 证明
Config/flags 代码路径本身无慢点；如需精确归因（Defender vs 冷缓存），需在受控环境
多次冷启复测，当前证据不足以支持任何改动。

## 3. 结论与建议

### 3.1 可行的净收益（低风险，合计约 0.4–0.9s 热启动）

1. **延迟导入 `first_run_dialog`**（热 ~76ms / 冷 ~253ms）：仅首跑使用，移入
   `if not config.is_initialized()` 分支内导入。已初始化用户**完全省去**。
2. **延迟导入 `shutil`**（热 ~39ms / 冷 ~141ms）：仅 crash log 迁移/清理使用，移入
   `_migrate_crash_logs` / `_cleanup_crash_logs` 函数内。正常启动路径完全省去。
3. **`markdown_it` / `markdown` 从 editor_tabs 顶层导入改为延迟**（~556ms，占热启动
   import 的 1/3）：预览链专用依赖，若 `markdown_preview` 的预览控制器可延迟创建，
   则主窗口创建阶段不再付出该成本。**需先读代码确认导入结构再实施**，归入后续
   编辑器分支的低风险批次。

### 3.2 明确不做的

- **`asyncio`（qasync）**：事件循环必须早于主窗口创建（WebView2 构造期
  `ensure_future` 依赖，见 main.py C3-B 注释），无法移出启动路径，总成本不变。
- **`PyQt6.QtWidgets` / `src.core.config`**：启动必需，无可优化空间。
- **冷启动 9.2s 配置初始化**：一次性异常值，不改代码（见 2.3）。

### 3.3 主窗口构造期（~1.44s 去掉导入后）的后续方向

构造期剩余成本需更细粒度 profile（cProfile 单轮即可，无需新依赖）。候选怀疑对象：
预览后端初始化、插件加载、Minimap、workspace 恢复。**不阻塞当前分支**，可在编辑器
健壮性批完成后再立项。

### 3.4 对 D6（大文件性能 flag 默认值）的说明

本报告的数据是**启动路径**测量，不能直接推导大文件编辑路径的 flag 默认值与阈值
（`virtual_scroll` / `lazy_highlight` / `async_highlight` / `lazy_loading` /
`large_file_mode`）。D6 决策需要另行做大文件实测（打开 10MB+ 文档的耗时与内存），
111.md 中「D6 依赖 1.6」应理解为依赖本次建立的**测量方法**，而非本报告数据。

> **D6 已决（2026-09-23，随编辑器健壮性批实测后拍板）**：`large_file_mode` 默认开启
> （阈值 `LARGE_FILE_THRESHOLD` = 1 万行），状态栏新增「大文件」指示标签；
> `virtual_scroll` / `lazy_loading` 两个死 flag 删除；`lazy_highlight` /
> `async_highlight` 维持按需激活。大文件感知性能治理（打开 / 切主题卡顿、预览占位）
> 同批完成，实测数据见 CHANGELOG v2.6.0「性能：感知性能批」。

## 4. 测量方法（可复现）

```powershell
# 模块导入（无 GUI，进程自然退出，stderr 完整）
.venv\Scripts\python.exe -X importtime -c "import main" 2> importtime.log

# 阶段耗时：正常启动应用，报告由 StartupProfiler 写入
# <数据目录>/data/logs/panzernote.log（搜索「启动性能报告」）
.venv\Scripts\python.exe -X importtime main.py
```

注意事项（实测踩坑）：

- GUI 实测需后台启动并等待报告落盘后 kill；**不要依赖被 kill 进程的 stderr 尾部**
  （块缓冲会丢数据，需 `-u` 或接受丢失）。
- 等待日志时必须要求日志**长度增长**后再匹配「启动性能报告」，否则会误匹配上一轮
  的旧报告。
- 同一数据目录同时只应有一个实例在跑，避免 autosave/workspace 相互覆盖。
