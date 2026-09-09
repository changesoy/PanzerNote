# Hand-off：方案 B — WebEngine 单路径 + 打包瘦身

> 对应分支：**`refactor20260910-webengine_single_path`**（尚未创建）
> 本文件是实施依据与交接文档，仓库根目录工作文档（沿用 Wave8-V1清理迁移方案.md 惯例）。

| 项         | 值                                                                    |
| ---------- | --------------------------------------------------------------------- |
| 基线       | `main @ c878f0b`（Merge PR #12，Wave 8 主题体系，v2.2.0，工作区干净） |
| 类型       | refactor（删除回退 + 打包配置优化）                                   |
| 风险       | 低                                                                    |
| 目标体积   | 538 MB → 约 300 MB（无功能损失）                                      |
| 与其他分支 | 基于 main 独立创建；不与方案 A 分支互相依赖（冲突处理见 §10）         |

---

## 1. 背景与决策

渲染系统存在双路径：`HAS_WEBENGINE` 为真走 `QWebEngineView`（完整功能），为假回退
`QTextBrowser`（降级功能）。分发形态为 PyInstaller onedir 且 WebEngine 必然打进包内，
回退分支在打包环境中不可达，属于死代码。

用户决策（2026-09-10 会话）：

1. 主线走方案 B：保留 WebEngine 为唯一渲染路径，**彻底删除**回退机制（不留废弃开关）。
2. 打包瘦身：spec 排除无用 Qt 模块、只保留中文翻译。
3. 方案 B 同样在独立实验分支上进行，成败不影响 main。

## 2. 基线现状（实测事实）

### 2.1 体积构成（dist\PanzerNote，PyInstaller 6.22.2，`--contents-directory .`）

| 部分                           | 大小                                                 |
| ------------------------------ | ---------------------------------------------------- |
| 总计                           | 538.2 MB                                             |
| PyQt6                          | 488.7 MB                                             |
| ├ Qt6\bin                      | 308.2 MB（最大单文件 Qt6WebEngineCore.dll 195.3 MB） |
| ├ Qt6\resources                | 101.4 MB（WebEngine ICU/快照）                       |
| ├ Qt6\translations             | 52.6 MB（几十种语言，仅需中文）                      |
| ├ Qt6\qml                      | 8.2 MB                                               |
| ├ Qt6\plugins                  | 4.3 MB                                               |
| PIL                            | 12.8 MB                                              |
| 其余（shiboken6/data/yaml 等） | < 3 MB                                               |

### 2.2 回退机制消费点（基线代码，删除依据）

| 文件                              | 位置                                             | 内容                                                         |
| --------------------------------- | ------------------------------------------------ | ------------------------------------------------------------ |
| `src/editor/markdown_preview.py`  | 46-54                                            | `HAS_WEBENGINE` 导入守卫                                     |
| 同上                              | 561-562                                          | `PreviewBrowser` 类定义                                      |
| 同上                              | 836-846                                          | 双路径初始化分支                                             |
| 同上                              | 855-860, 870-875, 891-893, 993, 1085, 1304, 1616 | 各处 `HAS_WEBENGINE and isinstance(...)` 分支                |
| 同上                              | 1633-1642                                        | QTextBrowser 比例滚动同步回退                                |
| `src/editor/export_service.py`    | 23-26, 111                                       | PDF 导出无引擎守卫                                           |
| `src/editor/webengine_runtime.py` | 13-19, 32-39                                     | `WEBENGINE_AVAILABLE` 守卫与启动锚点                         |
| `tests/test_markdown_preview.py`  | 263-276, 350-356                                 | `PreviewBrowser` 浮层测试 + patch `HAS_WEBENGINE=False` 测试 |

删除范围需在实施时用 Grep 复核（`HAS_WEBENGINE`/`WEBENGINE_AVAILABLE`/`PreviewBrowser`
src+tests 全量 0 命中，历史文档除外）。

### 2.3 WebEngine 依赖面（裁剪红线）

`Qt6WebEngineQuick.dll` 与 `qml/` 目录随包存在说明 WebEngine 运行依赖 Qt Quick/Qml。
红线：**不得**整体排除 `QtQuick`、`QtQml`、`QtPositioning`（WebEngine 地理定位相关），
除非排除后经启动 + 预览真机验证明确可用。

## 3. 目标 / 非目标

**目标**

- WebEngine 成为唯一渲染路径，代码单一化。
- 打包产物瘦身至约 300 MB，功能与观感零变化。
- 新增打包体积测量命令，使每次构建的体积可复核。

**非目标**

- 不更换渲染引擎（那是方案 A 分支）。
- 不改任何渲染行为、主题观感、导出格式。
- 不处理游戏侧图片体积（独立主题，见 roadmap）。
- 不做 onefile；保持 onedir + `--contents-directory .`。
- 不做版本号 bump（版本决策属于发布收尾，见 `panzernote-versioning`）。

## 4. 实施阶段

每批：实现 → 全量 tiered pytest（`pytest-tiered-timeout-hunter`）→ 全量 mypy
（`.venv\Scripts\mypy.exe src/`）→ 报告。打包相关批次额外执行启动验证。

### B1 基线重建（0 代码变更）

- 用当前 `PanzerNote.spec` 重新构建，记录基线体积与 `data/assets` 完整性。
- 记录 warn 文件：`build\PanzerNote\warn-PanzerNote.txt`。
- 产出：体积测量基线（应以 538.2 MB 为参照）。

### B2 裁剪实验（一批只动一个候选，逐批验证）

候选排除清单（写入 spec 的 `excludes`）：

| 候选                            | 理由                       | 注意                            |
| ------------------------------- | -------------------------- | ------------------------------- |
| `PyQt6.QtQuick3D`               | 项目未使用 3D              | 需验证不为 WebEngine 传递依赖   |
| `PyQt6.QtMultimedia*`           | 无音视频播放功能           | 同上                            |
| `PyQt6.QtSensors`               | 未使用                     | 同上                            |
| `PyQt6.QtSerialPort`            | 未使用                     | —                               |
| `PyQt6.QtSpatialAudio`          | 未使用                     | 同上                            |
| `PyQt6.QtStateMachine*`         | 未使用                     | 同上                            |
| `PyQt6.QtTextToSpeech`          | 无 TTS 功能                | 需确认 WebEngine 不强依赖       |
| translations 裁剪               | 只留 `qt_zh_CN.qm` 与 base | 通过 spec 数据操作或自定义 hook |
| Pygments lexer 裁剪（可选进阶） | 只打包项目用到的 lexer     | 自定义 hook 成本略高            |
| PIL 插件裁剪（可选进阶）        | 保留所需格式               | 收益小，可跳过                  |

每批验证：构建 → 启动 exe → Markdown 预览渲染 → 导出 PDF → 主题明暗切换 →
记录新体积。任一异常即撤销该候选。若一个候选让体积变化 < 1 MB 且无明确依据，跳过。

### B3 彻底删除回退机制

- `markdown_preview.py`：删 `HAS_WEBENGINE` 守卫、`_WEBENGINE_IMPORT_ERROR`、
  `PreviewBrowser` 类、所有 `isinstance` 二选一分支、比例滚动回退；
  `self.preview` 收敛为 `QWebEngineView` 固定类型。
- `export_service.py`：删 `HAS_WEBENGINE` 守卫，`printToPdf` 为唯一路径。
- `webengine_runtime.py`：删 `WEBENGINE_AVAILABLE` 守卫与不可达分支（锚点机制保留）。
- `main.py`：`AA_ShareOpenGLContexts` 与注释保留（导入时序仍需要）。
- 删除前 Grep 复核 `highlight_code_html` 等"QTextBrowser 适用"函数是否有其他消费方
  （HTML 导出路径可能复用），再决定去留。
- 测试：删/改写 `tests/test_markdown_preview.py` 263-276、350-356；全量其余测试
  不得有回退语义残留。

### B4 终验与文档

- 体积对比表：B2 各候选收益汇总；给出最终测量结果。
- 真机 GUI smoke（参照 `panzernote-ui-regression-checklist` 核心启动 + Markdown 预览项）。
- 文档同步：`docs/architecture.md` 中 Markdown 预览/导出的双路径描述改为单路径。
  若提前在开发中同步也可（`panzernote-pre-pr-workflow` 映射变更类型）。

## 5. 关键文件清单

| 文件                              | 改动                    |
| --------------------------------- | ----------------------- |
| `PanzerNote.spec`                 | excludes + 翻译裁剪逻辑 |
| `src/editor/markdown_preview.py`  | 回退机制全删            |
| `src/editor/export_service.py`    | PDF 守卫全删            |
| `src/editor/webengine_runtime.py` | 可用性守卫全删          |
| `main.py`                         | 复核（预计无改动）      |
| `tests/test_markdown_preview.py`  | 回退测试删除/改写       |
| `docs/architecture.md`            | 单路径描述同步          |

## 6. 验收标准

- [ ] Grep `HAS_WEBENGINE`/`WEBENGINE_AVAILABLE`/`PreviewBrowser` 于 src+tests 0 命中
- [ ] 全量 tiered pytest 通过；全量 mypy 零错误
- [ ] 打包体积 ≤ 320 MB（目标约 300 MB），`data/assets` 完整
- [ ] 目标机启动正常：预览、PDF 导出、明暗主题、插件 4 项手工验证通过
- [ ] WebEngine 加载失败 = 预览不可用（接受的行为变化，写入 CHANGELOG 说明）

## 7. 风险与回滚

- 每批独立提交，B2 任一候选可单独 revert。
- 最大风险点：误排除 WebEngine 传递依赖 → 启动失败无提示（windowed）。缓解：
  每批验证 + 必查 `warn-PanzerNote.txt`。
- 回退删除后无法降级运行（接受，属目标行为）；若将来需要无 WebEngine 形态，
  由方案 A 分支覆盖解决。

## 8. 验证命令

```powershell
# 构建
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean PanzerNote.spec

# 体积测量
$d = (Get-ChildItem -Recurse -File 'dist\PanzerNote' | Measure-Object -Property Length -Sum).Sum
'{0:N1} MB' -f ($d / 1MB)

# 测试与类型检查（详见 pytest-tiered-timeout-hunter / python-virtualenv-quick-reference）
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\mypy.exe src/
```

注意：PyInstaller 日志实测 Python 3.14.7（`C:\Python314`）；与
`python-virtualenv-quick-reference` 记载的 3.11 不一致。分支开工前用
`python --version` 复核环境，再决定构建矩阵。

## 9. 版本与文档

- 分支内**不**做版本 bump；`src/__init__.py::__version__` 保持 2.2.0，
  发布收尾按 `panzernote-versioning` / `panzernote-pre-pr-workflow` 处理。
- CHANGELOG 记录"删除预览回退、打包瘦身"及其行为含义（预览不再降级可用）。

## 10. 与其他分支的关系

- 与方案 A（`refactor20260910-lightweight_preview`）均从 `main @ c878f0b` 创建，互不依赖。
- 建议 B 先行合入（低风险）。若 A 之后合入，A 会重新引入 QTextBrowser 并替换 B 的
  "删除回退"成果（预期，不视为冲突损失）；B 的打包裁剪成果由 A 继承并去掉
  WebEngine 相关排除项。
