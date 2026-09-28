# PanzerNote 开发者指南

面向参与 PanzerNote 开发的贡献者，覆盖环境搭建、日常开发循环、测试与提交规范。
架构细节（模块职责、数据流、约束依据）见 [architecture.md](architecture.md)，
本文只做索引与操作指引。

## 环境搭建

要求：Python 3.11+、Windows 10/11、Microsoft Edge WebView2 Runtime（预览与 PDF 导出）。

```bash
python -m venv .venv
.venv\Scripts\pip install -e ".[all]"   # 完整安装（核心 + 格式化 + 开发/测试依赖）
```

可选依赖分组见 `pyproject.toml`：`format`（格式化相关）、`dev`（pytest / mypy 等）、
`all`（前两组之和）。核心依赖中的 `pillow-heif`（HEIF / HEIC 解码）自带原生库，
打包产物会因此增大约 27 MB。

## 日常开发循环

```bash
.venv\Scripts\python.exe main.py          # 运行
.venv\Scripts\pytest.exe -v               # 测试
.venv\Scripts\mypy.exe src/               # 类型检查
.venv\Scripts\python.exe -X importtime main.py   # 启动耗时分析
```

### 测试约定

- `tests/` 目录被 `.gitignore` 忽略，**不入库**，但本地必须维护并随代码更新。
- 全量回归建议带超时运行：`pytest --timeout=25`。Windows 下 pytest 超时会终止
  整个测试进程，超时用例视为未执行；对个别慢用例可提高该用例的超时或单独复核。
- UI 相关改动无法完全被自动化覆盖，需按受影响界面手工核验
  （启动 / 主题 / 编辑器 / 预览 / 分屏 / 面板 / 对话框等，参见改动面清单）。

### 诚实验证

未实际执行的测试、类型检查、UI 核验或迁移，不得声称通过；无法执行时说明原因，
并给出可自行执行的完整命令。

## 项目结构

```
main.py                  # 入口
src/
  core/                  # 配置（Config 门面）、快捷键、存档、文档注册等
  editor/                # 编辑器核心、标签页、预览、图片工作流、搜索等
  ui/                    # 主窗口、面板宿主、对话框、视图协调
  game/                  # 游戏侧栏、秘书、资源等游戏系统
  themes/                # Theme v2 主题引擎与校验
  plugins/               # 可信插件系统
  security/              # PathValidator / FileGuard / InputValidator
  platform/ utils/ data/ notebooks/  # 平台适配、工具、内置数据
data/help/               # 应用内帮助（manual.md / guide.md）
docs/                    # 仓库级文档（本文所在）
plugins/                 # 插件 API 文档与示例
scripts/                 # 打包、版本校验等工具脚本
```

完整目录树与每个模块的职责说明见 [architecture.md §3 / §4](architecture.md)。

## 版本管理

- `src/__init__.py::__version__` 是**唯一版本真相源**，语义化版本（SemVer）。
- 版本 bump 只在发布收尾时统一进行，不随每个功能提交递增；
  同步更新 `CHANGELOG.md`。
- `scripts/verify_version.py` 可校验版本一致性。

## 提交规范

- 分支命名：`<type><YYYYMMDD>-<snake_case_topic>`，type ∈
  `feat fix refactor perf docs test chore`，如 `feat20260923-editor_robustness`。
- 提交信息首行 `<type>(<scope>): <中文摘要>`，正文用中文说明改了什么、为什么、
  行为影响；有测试 / 验证 / 文档影响时单列小节注明。
- 提交边界 = 一个已验证的连贯阶段（实现 → 全量测试 → 类型检查 → 提交）。
- 不做未经批准的破坏性 git 操作；`--force`、`reset --hard` 等仅在明确必要时使用，
  误操作恢复流程见 [branch_recovery.md](branch_recovery.md)。

## 架构约束摘要

以下为高频红线（完整依据见 [architecture.md §10](architecture.md)）：

- 文档状态归 `SharedDocument` / `ViewState`，不得引入每标签影子状态。
- 不得绕过 `PathValidator` / `FileGuard` / `InputValidator`。
- 不得改变文件编码保持行为（除非明确批准）。
- 不在非主线程操作 PyQt UI 对象；快捷键与菜单动作走既有
  `ShortcutManager` / `MenuBuilder` 机制。
- 持久化 schema（savegame / settings / workspace）不得静默变更。
- 保持离线本地化，不新增网络行为。
- 主题相关改动使用 token / recipe 体系，不硬编码颜色；QSS 生成以 v2 激活变体为
  唯一真相源（主题作者契约见 [theme_authoring.md](theme-design/theme_authoring.md)）。

## 文档地图

| 文档 | 内容 |
| --- | --- |
| [architecture.md](architecture.md) | 模块结构、核心模块详解、数据流、架构约束 |
| [user_guide.md](user_guide.md) | 终端用户指南 |
| [roadmap.md](roadmap.md) | 未完成规划 |
| [memorandum.md](memorandum.md) | 暂不排期的技术判断留档 |
| [branch_recovery.md](branch_recovery.md) | Git 误操作恢复与应用数据恢复 |
| [startup_performance.md](startup_performance.md) | 启动性能实测结论 |
| [theme-design/](theme-design/) | 主题作者指南、颜色审计、Wave 8 验收 |
| [archive/](archive/) | 已归档的历史设计稿（非现行真相源） |
| [../plugins/plugin_api.md](../plugins/plugin_api.md) | 插件生命周期、权限、API 参考 |
| [../CHANGELOG.md](../CHANGELOG.md) | 版本变更记录 |

## 打包

`scripts/build_package.py` 生成 PyInstaller 冻结产物。注意 `pillow-heif` 的原生库
会使产物体积增大约 27 MB（98.8 MB → 126.3 MB），第三方许可与随包分发义务见
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
