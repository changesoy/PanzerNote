# Hand-off：方案 A — 轻量渲染（去 WebEngine）

> 对应分支：**`refactor20260910-lightweight_preview`**（尚未创建）
> 本文件是实施依据与交接文档，仓库根目录工作文档（沿用 Wave8-V1清理迁移方案.md 惯例）。

| 项         | 值                                                                    |
| ---------- | --------------------------------------------------------------------- |
| 基线       | `main @ c878f0b`（Merge PR #12，Wave 8 主题体系，v2.2.0，工作区干净） |
| 类型       | refactor（渲染引擎替换，架构级变更）                                  |
| 风险       | 高（触发项目约束的高风险审批门槛：架构方向需用户决策）                |
| 目标体积   | 约 60–100 MB（去除 WebEngine 约 400 MB）                              |
| 与其他分支 | 基于 main 独立创建；与方案 B 互斥（冲突处理见 §10）                   |

---

## 1. 背景与决策

打包产物 538 MB 的约 400 MB 来自 Qt WebEngine（Chromium 内核），是体积上限的主因。
轻量化路线：去掉 `PyQt6.QtWebEngineWidgets`，强化现存 `QTextBrowser` 路线成为唯一
渲染路径，用 Qt 原生 `QTextDocument` 渲染 `markdown-it-py` 生成的 HTML。

用户决策（2026-09-10 会话）：

1. 方案 A 在独立实验分支进行（副本尝试），成败不影响 main。
2. 先看效果再定：首个可交付物是渲染观感对比（vertical slice），由用户决策是否继续。
3. 方案 C（reportlab 自绘 PDF）仅当 A 的 Qt 原生打印（`QPdfWriter`）效果不满足时启用，属兜底选项。

## 2. 基线现状（映射到改动面）

### 2.1 现有可复用资产

| 资产           | 位置                                                                              | 说明                                                                            |
| -------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| 双路径外壳     | `src/editor/markdown_preview.py:46-54, 561-562`                                   | `HAS_WEBENGINE` 守卫 + `PreviewBrowser`（现为打包死代码，A 将其扶正为唯一路径） |
| md → HTML 管线 | `src/editor/secure_markdown_renderer.py`（markdown-it-py + 净化）                 | **不变**：继续产出 HTML，仅渲染端改变                                           |
| 内联样式高亮   | `src/editor/highlight_themes.py`（Pygments formatter，标注"适用于 QTextBrowser"） | 现成，供 QTextDocument 渲染                                                     |
| 比例滚动同步   | `markdown_preview.py:1633-1642`                                                   | 已有的非引擎行号同步 fallback，需强化精度                                       |
| CSS 模板       | `secure_markdown_renderer.MARKDOWN_LAYOUT_CSS`                                    | 使用 `:root` 变量/现代 CSS，QTextDocument 只支持有限子集，需转换                |
| PDF 导出       | `src/editor/export_service.py:23-26, 111, 129`                                    | 现走 `printToPdf`；A 改为 `QPdfWriter` + `QTextDocument.print()`                |

### 2.2 体积对照

| 路线                                 | 预计体积             |
| ------------------------------------ | -------------------- |
| 现状                                 | 538 MB               |
| 仅方案 B 打包瘦身                    | 约 300 MB（上限）    |
| 方案 A（去 WebEngine + 继承 B 成果） | 约 60–100 MB（目标） |

## 3. 目标 / 非目标

**目标**

- 渲染唯一化到 QTextBrowser（QTextDocument）+ 现有 HTML 管线。
- 体积进入 60–100 MB 区间。
- 预览核心功能保留：Markdown 常见语法、代码高亮、本地图片、明暗主题、复制按钮。
- PDF 导出以 `QPdfWriter` + `QTextDocument.print()` 替换 `printToPdf`。

**非目标**

- 不做 onefile。
- 不重写 markdown 解析与净化（管线不动，安全边界不动）。
- 不自研渲染器（明确否决）。
- 不追求与 Chromium 逐像素一致的观感；以"可用且体面的 md 编辑器观感"为合格线。

## 4. 实施阶段

架构级变更，每批：实现 → 全量 tiered pytest → 全量 mypy → 报告 →
重大效果/决策点先给用户看再继续。入库前不 bump 版本。

### A0 垂直切片原型（决策门）

- 独立原型脚本（建议 `scripts/proto_qtextbrowser_preview.py`，不碰主代码）：
  取 2-3 份代表性 md 样例（标题/表格/代码块/图片/引用），用 markdown-it-py 出 HTML，
  QTextBroswer 渲染 + 现成内联高亮 + CSS 子集，截图或真机展示与 WebEngine 对比。
- 用户决策：观感通过 → A1；不通过 → 分支停止（失败代价仅限分支本身）。

### A1 主题 CSS 转换与预览集成

- 把现有 CSS 模板转成 QTextDocument 支持的子集（无 flex/grid/:root 变量，
  用具体值注入）；双主题 token 消费维持现状（可能复用主题引擎输出而非 CSS 变量）。
- `markdown_preview.py` 内 `self.preview` 改为 `PreviewBrowser`，删除 WebEngine 分支
  的 `isinstance` 判断（可借用方案 B 的删除清单反向操作）。
- 涉及预览观感 → 对照 `panzernote-ui-regression-checklist` 核心项。

### A2 交互能力替代

- 行号同步：优先强化比例滚动；必要时用 QTextDocument 块扫描做对应行定位。
- 复制按钮浮层：代码块复制以 Qt 原生信号/事件替代 JS（参考现 PreviewBrowser
  的 `_copy_code_btn` 实现，必要时重写为纯 widget 方案）。
- 现有依赖 JS 的能力逐项盘点：点击锚点、图片缩放、折叠——按"保留/降级/暂缓"
  清单决策后实施。

### A3 PDF 导出替换

- `QPdfWriter` + `QTextDocument.print()` 渲染导出 HTML（导出文档由
  `build_export_qtext_html_document` 构建，复用 `MARKDOWN_LAYOUT_CSS` 的 CSS 子集转换）。
- 与原 `printToPdf` 效果对比：分页、中文字体、代码块换行三个检查点。
- 效果不足 → 决策点：启用方案 C（reportlab 自绘）前必须经用户确认。

### A4 依赖摘除

- 移除 `PyQt6-WebEngine`：`pyproject.toml` 与 `requirements.txt` 同步（依赖变更
  走 `dependency-and-package-guard`）。
- 删除 `webengine_runtime.py`、`main.py` 中 `AA_ShareOpenGLContexts` 及导入时序注释。
- `PanzerNote.spec`：删除 WebEngine 相关收集；继承方案 B 的排除清单。
- `tests/test_theme_v2_smoke.py` 等引用 `QWebEngineView` 抓帧的测试改写。

### A5 终验与文档

- 体积验收 + 双主题视觉验收 + 打包真机 smoke。
- 文档：`docs/architecture.md` 渲染/预览/导出章节改写；`docs/roadmap.md`
  标记完成或终止；`CHANGELOG.md` 记录体积与观感变化。

## 5. 关键文件清单

| 文件                                                        | 改动                                                                   |
| ----------------------------------------------------------- | ---------------------------------------------------------------------- |
| `scripts/proto_qtextbrowser_preview.py`（新，A0 后已删除）  | A0 原型，验证后删除                                                    |
| `src/editor/markdown_preview.py`                            | 渲染唯一化、同步/交互替代                                              |
| `src/editor/secure_markdown_renderer.py`                    | CSS 子集转换（管线不动）                                               |
| `src/editor/export_service.py`                              | QPdfWriter 替换 printToPdf                                             |
| `src/editor/webengine_runtime.py`                           | 删除                                                                   |
| `main.py`                                                   | WebEngine 相关导入与时序删除                                           |
| `pyproject.toml` / `requirements.txt`                       | 摘除 PyQt6-WebEngine                                                   |
| `PanzerNote.spec`                                           | WebEngine 收集删除、排除清单继承                                       |
| `tests/`                                                    | 两分支共用，按实现能力门控（`@a_only` / `@webengine_only` / 构造签名） |
| `docs/architecture.md` / `docs/roadmap.md` / `CHANGELOG.md` | 同步                                                                   |

## 6. 验收标准

- [x] A0 决策门通过（用户确认观感）
- [x] 全量 tiered pytest 通过；全量 mypy 零错误（最终：pytest 1457 passed / 17 skipped，mypy 123 源文件 0 错误）
- [x] `src/` 中 `QWebEngineView`/`QtWebEngineWidgets`/`HAS_WEBENGINE` 0 命中。
      `tests/` 因两分支共用同一份用例，保留 B 侧等价用例并按实现门控
      （`@webengine_only` 在 A 上跳过，不执行 WebEngine import）
- [x] 打包体积 ≤ 100 MB 且 `data/assets` 完整（实测 90.1 MB，无 WebEngine / QML / `opengl32sw.dll` 残留）
- [x] 预览：常见 md 语法、代码高亮、图片、复制按钮、双主题可用（A2 三轮真机复测通过）
- [x] PDF 导出与 printToPdf 版本对照三项检查点通过（或用户接受差异）（A3 真机复测通过）

> 尚未完成：打包产物真机 smoke（`dist\PanzerNote-A-Light\PanzerNote.exe`，重点验证删除
> `opengl32sw.dll` 无副作用）与 PR 收尾（版本 bump + PR 文本），见执行文档 `111.md`。

## 7. 风险与回滚

- QTextDocument CSS 子集限制导致观感降级（最大风险）→ A0 先行验证观感，前置止损。
- 行号同步/交互为 JS → Qt 原生改写，工作量与效果均不确定 → A2 按"保留/降级/暂缓"
  清单决策，可接受降级项须用户确认。
- 每批独立提交；任一阶段中止即可保留已验证成果，不影响 main。
- 不做静默依赖删除：摘除 PyQt6-WebEngine 前全量 Grep 复核。

## 8. 验证命令

```powershell
# 原型：A0 完成后已删除（依赖 WebEngine 与已删模板，不可再运行）
# scripts/proto_qtextbrowser_preview.py

# 构建与体积
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean PanzerNote.spec
$d = (Get-ChildItem -Recurse -File 'dist\PanzerNote' | Measure-Object -Property Length -Sum).Sum
'{0:N1} MB' -f ($d / 1MB)

# 保留产物以便与方案 B 快速对比（B 已存为 dist\PanzerNote-B-WebEngine）
# 注意：-NewName 只给名称，不能带路径
Rename-Item -Path dist\PanzerNote -NewName PanzerNote-A-Light

# 测试与类型检查（详见 pytest-tiered-timeout-hunter / python-virtualenv-quick-reference）
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\mypy.exe src/
```

环境注意同上：打包实测 Python 为 3.14.7，开工前用 `python --version` 复核。

## 9. 版本与文档

- 分支内不 bump 版本（若合入则类型为架构变更，版本决策届时按
  `panzernote-versioning` 处理）。
- 架构文档属"下一实施阶段依赖的事实来源"，A5 前必须同步完毕。

## 10. 与其他分支的关系

- 与方案 B（`refactor20260910-webengine_single_path`）均从 `main @ c878f0b` 创建。
- B 先合入后，A 合入时会覆盖 B 的"删除回退"成果（A 重新引入 QTextBrowser 且删除
  WebEngine）；B 的打包排除清单由 A 继承并移除 WebEngine 相关项。
- 若 A 中止，B 成果独立有效，main 不受影响。
