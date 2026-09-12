# Third-Party Notices

本文件记录 PanzerNote 直接依赖的第三方组件及其许可证（Wave 8 B9 license 合规）。

PanzerNote 自身许可证：GPL-3.0-or-later（见 `LICENSE`）。

## 运行时依赖（requirements.txt / pyproject.toml）

| 组件                                 | 版本约束              | 许可证                                         | 用途                                                                     |
| ------------------------------------ | --------------------- | ---------------------------------------------- | ------------------------------------------------------------------------ |
| PyQt6                                | >=6.11.0              | GPL-3.0（Riverbank Computing，另提供商业授权） | Qt 绑定 / GUI 框架                                                       |
| shiboken6                            | >=6.11.2              | LGPL-3.0                                       | PyQt6 绑定支撑库                                                         |
| Pygments                             | >=2.21.0              | BSD-2-Clause                                   | 语法高亮                                                                 |
| markdown (Python-Markdown)           | >=3.10.3              | BSD-3-Clause                                   | Markdown 渲染（导出 fallback）                                           |
| Pillow                               | >=12.3.0              | HPND（MIT-CMU 风格，含自由再分发条款）         | 图像处理                                                                 |
| send2trash                           | >=2.1.0               | BSD-3-Clause                                   | 文件树删除到回收站                                                       |
| markdown-it-py                       | >=4.2.0               | MIT                                            | Markdown 主渲染引擎                                                      |
| mdit-py-plugins                      | >=0.6.1               | MIT                                            | Markdown 扩展语法（定义列表/任务列表）                                   |
| qasync                               | >=0.28.0              | BSD-2-Clause                                   | 把 asyncio 与 Qt 事件循环合并到同一线程（WebView2 后端前提）             |
| webview2-Microsoft.Web.WebView2.Core | >=3.2.1               | MIT                                            | PyWinRT 官方投影的 WebView2 Core API（Markdown 预览 / PDF 导出后端）     |
| winrt-Windows.Foundation             | >=3.2.1               | MIT                                            | PyWinRT 的 `Windows.Foundation` 命名空间（Rect / 异步类型）              |
| winrt-runtime                        | ~=3.2.1.0（传递依赖） | MIT                                            | PyWinRT 运行时（`winrt.system`），随上述 `webview2-*` / `winrt-*` 包引入 |

> 说明：Markdown 预览与 PDF 导出经系统安装的 **Microsoft Edge WebView2 Runtime** 承载。
> 该 Runtime 由操作系统 / Microsoft Edge 提供，**不随 PanzerNote 分发**，故不列入本表；
> 缺失时的只读检测与安装指引见 `src/editor/webview2_runtime.py`。
> `qasync` / `webview2-*` / `winrt-*` 均为 Windows 专用。
> 许可证依据：`qasync` 包元数据 `License-Expression: BSD-2-Clause`（作者 Arve Knudsen 等，
> 上游 https://github.com/CabbageDevelopment/qasync ）；`webview2-*` / `winrt-*` 包元数据
> `License-Expression: MIT`（PyWinRT 官方投影，上游 https://github.com/pywinrt/pywinrt ）。

## 内置资产（随源码仓库引入）

与 pip 依赖不同，这些文件直接随仓库分发，许可证文本各随其目录。

| 资产  | 版本   | 许可证 | 用途与位置                                                             |
| ----- | ------ | ------ | ---------------------------------------------------------------------- |
| KaTeX | 0.18.7 | MIT    | 数学公式渲染；`data/assets/vendor/katex/`（katex.min.js / katex.min.css / fonts/*.woff2 / LICENSE） |

> 说明：KaTeX 样式与脚本在运行时**内联**进预览模板与导出的 HTML，字体转 data URI，
> 因此预览与导出文件都是自包含的（断网可用，无 CDN 请求），符合「零运行时网络依赖」。
> 升级时替换 `data/assets/vendor/katex/` 下的文件并同步本表版本号。

## 可选依赖（格式化）

| 组件                         | 许可证 |
| ---------------------------- | ------ |
| PyYAML                       | MIT    |
| tomli                        | MIT    |
| tomli-w                      | MIT    |
| cssbeautifier (jsbeautifier) | MIT    |
| html5lib                     | MIT    |

## 开发依赖

| 组件           | 许可证 |
| -------------- | ------ |
| pytest         | MIT    |
| pytest-cov     | MIT    |
| pytest-qt      | MIT    |
| pytest-timeout | MIT    |
| mypy           | MIT    |

## 资产（当前未随源码仓库引入）

以下资产在 Wave 8 设计中列为候选，**尚未引入仓库**；正式引入时须随资产文件一并落许可证文本：

| 资产                     | 许可证  | 用途                        |
| ------------------------ | ------- | --------------------------- |
| Lucide（图标集）         | ISC     | 内置 IconRegistry（D5/D24） |
| Inter（字体）            | OFL-1.1 | UI 拉丁字体（D5/D25）       |
| 思源黑体 Source Han Sans | OFL-1.1 | UI 中文字体（D5/D25）       |
| JetBrains Mono（字体）   | OFL-1.1 | 代码等宽字体（D5/D25）      |

> 说明：以上资产未打包进任何发布产物，亦不在 `dist/` 源码包内；引入时在
> `themes/` 或 `data/assets/` 对应目录放置许可证副本并更新本文件。

## 合规要点

- 运行与发布均**零运行时网络依赖**（D4）：无 CDN / 远程字体 / 远程图标加载。
- 分发形态为源码包（`dist/PanzerNote-<ver>-src.zip`），GPL-3.0 依赖（PyQt6）在
  源码分发下无链接例外问题；若未来做二进制冻结分发（PyInstaller），需复核 PyQt6
  GPL 合规与 Qt 组件许可边界。
- 摘除 Qt WebEngine / Chromium 后，冻结产物不再包含 PyQt6-WebEngine（GPL-3.0）；
  预览侧新增的 `webview2-*` / `winrt-*`（MIT）与 `qasync`（BSD-2-Clause）均为宽松
  许可，系统 WebView2 Runtime 不随包分发、无需在本仓库登记再分发条款。
