# -*- coding: utf-8 -*-
"""A0 垂直切片原型：QTextBrowser（QTextDocument CSS 子集） vs WebEngine（完整 CSS）观感对比

方案 A 决策门原型（handoff-lightweight_preview.md §4-A0）：
- 左栏：WebEngine 完整 CSS 渲染（现有 PREVIEW_HTML_TEMPLATE 观感，含 :root 变量/伪类/布局）
- 右栏：QTextBrowser（QTextDocument CSS 子集）渲染
- 底部：明暗主题切换（ThemeManager L0）+ 3 份样例切换 + 截图导出

独立脚本，不触碰主代码。代码高亮两侧共用 highlight_code_html
（Pygments 内联样式，同一高亮源），观感差异只来自容器 CSS 支持度。

用法：
    .\\.venv\\Scripts\\python.exe scripts/proto_qtextbrowser_preview.py
    .\\.venv\\Scripts\\python.exe scripts/proto_qtextbrowser_preview.py --sample 2
    .\\.venv\\Scripts\\python.exe scripts/proto_qtextbrowser_preview.py --screenshot shot.png --sample 1
    .\\.venv\\Scripts\\python.exe scripts/proto_qtextbrowser_preview.py --no-webengine
"""
from __future__ import annotations

import argparse
import html as html_module
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ── QApplication 创建前：按 main.py 惯例预置 WebEngine 导入前提 ──
from PyQt6.QtCore import Qt, QTimer, QUrl  # noqa: E402

from src.themes.theme_v2.consumer import v2_color, v2_token  # noqa: E402
from src.themes.theme_v2.manager import ThemeManager  # noqa: E402
from src.themes.theme_v2.service import ThemeV2Service  # noqa: E402
from src.editor.highlight_themes import highlight_code_html  # noqa: E402
from src.editor.secure_markdown_renderer import (  # noqa: E402
    MARKDOWN_LAYOUT_CSS,
    convert_layout_css_for_qtext,
    render_markdown_to_safe_html,
)

# ════════════════════════════════════════════════════════
#  常量（与 markdown_preview.py 保持一致的复制品，原型自包含）
# ════════════════════════════════════════════════════════

_CODEBLOCK_RE = re.compile(
    r'<pre(?P<pre_attrs>[^>]*)>\s*'
    r'<code(?P<code_attrs>[^>]*)>'
    r'(?P<body>.*?)'
    r'</code>\s*</pre>',
    re.DOTALL | re.IGNORECASE,
)
_IMG_SRC_RE = re.compile(r'(<img\s[^>]*?)src="([^"]*)"', re.IGNORECASE)


def _extract_language_from_code_attrs(attrs: str) -> str:
    m = re.search(r'class="([^"]*)"', attrs or "")
    if not m:
        return ""
    classes = m.group(1).split()
    for cls in classes:
        if cls.startswith("language-"):
            return cls.removeprefix("language-")
        if cls.startswith("lang-"):
            return cls.removeprefix("lang-")
    return ""


# ════════════════════════════════════════════════════════
#  主题 shim（ThemeEngine 最小替代，供 consumer 取 v2 值）
# ════════════════════════════════════════════════════════


class _ThemeShim:
    """仅挂载 theme_v2 的轻量对象：v2_token/v2_color/v2_syntax_colors 只需该属性。"""

    def __init__(self, svc: ThemeV2Service) -> None:
        self.theme_v2 = svc


# ════════════════════════════════════════════════════════
#  CSS 子集转换（复用生产实现，见 secure_markdown_renderer）
# ════════════════════════════════════════════════════════


def qtext_theme_colors(shim) -> dict[str, str]:
    """QTextDocument 子集 CSS 的变量色值（与 markdown_preview._qtext_theme_colors 一致）。"""
    return {
        "text-primary": v2_token(shim, "text_primary", "#212121"),
        "text-secondary": v2_token(shim, "text_secondary", "#757575"),
        "text-muted": v2_token(shim, "text_muted", "#BDBDBD"),
        "border": v2_token(shim, "border_muted", "#E0E0E0"),
        "border-soft": v2_token(shim, "border_muted", "#EEEEEE"),
        "divider": v2_token(shim, "border_muted", "#EEEEEE"),
        "surface": v2_token(shim, "surface_secondary", "#F5F5F5"),
        "surface-soft": v2_token(shim, "surface_secondary", "#F5F5F5"),
        "surface-hover": v2_token(shim, "surface_raised", "#FAFAFA"),
        "primary": v2_token(shim, "accent", "#2196F3"),
        "primary-hover": v2_token(shim, "focus", "#1976D2"),
        "bg-codeblock": v2_token(shim, "md_preview_code_block_bg", "#EDF3FA"),
        "scrollbar-thumb-hover": v2_color(shim, "scrollbar", "handle_hover", "#BDBDBD"),
    }


# ════════════════════════════════════════════════════════
#  HTML 构建
# ════════════════════════════════════════════════════════


def resolve_images(html: str, base_dir: Path) -> str:
    """相对图片路径 → file:// 绝对路径（与 markdown_preview._resolve_local_images 同语义）。"""

    def _resolve(m):
        prefix, src = m.group(1), m.group(2)
        if src.startswith(("http://", "https://", "file://", "data:")) or os.path.isabs(src):
            return m.group(0)
        abs_path = os.path.normpath(os.path.join(str(base_dir), src))
        if os.path.exists(abs_path):
            return f'{prefix}src="{QUrl.fromLocalFile(abs_path).toString()}"'
        return m.group(0)

    return _IMG_SRC_RE.sub(_resolve, html)


def _highlight_block(m, shim) -> str:
    attrs = m.group("code_attrs") or ""
    lang = _extract_language_from_code_attrs(attrs)
    raw = html_module.unescape(m.group("body")).rstrip("\n")
    return highlight_code_html(raw, lang, shim)


def process_code_blocks_qtext(html: str, shim) -> str:
    """QTextBrowser 侧：<pre> 容器 + 内联 style（与生产 _qtext_code_container_style 一致）。"""

    def _replace(m):
        bg = v2_token(shim, "md_preview_code_block_bg", "#EDF3FA")
        border = v2_token(shim, "border_muted", "#D8DEE9")
        fg = v2_token(shim, "text_primary", "#212121")
        highlighted = _highlight_block(m, shim)
        return (
            f'<pre style="background-color:{bg};border:1px solid {border};'
            f'padding:10px;color:{fg};font-family:Consolas,\'Courier New\',monospace;'
            f'font-size:14px;line-height:1.55;">{highlighted}</pre>'
        )

    return _CODEBLOCK_RE.sub(_replace, html)


def process_code_blocks_web(html: str, shim) -> str:
    """WebEngine 侧：code-container 容器（对应 PREVIEW_HTML_TEMPLATE 的 class 样式）。"""

    def _replace(m):
        highlighted = _highlight_block(m, shim)
        return (
            '<div class="code-container"><pre class="code-pre">'
            f'<code class="code-block">{highlighted}</code></pre></div>'
        )

    return _CODEBLOCK_RE.sub(_replace, html)


def build_qtext_html(md_text: str, shim, base_dir: Path) -> str:
    """QTextDocument 子集 HTML：<style> 块 + 具体色值 + body 背景。"""
    body = render_markdown_to_safe_html(md_text)
    body = resolve_images(body, base_dir)
    body = process_code_blocks_qtext(body, shim)
    css = convert_layout_css_for_qtext(qtext_theme_colors(shim))
    bg = v2_token(shim, "surface_primary", "#FFFFFF")
    fg = v2_token(shim, "text_primary", "#212121")
    return (
        "<html><head><style>\n"
        "body { font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; font-size: 14px; line-height: 1.7; }\n"
        f"{css}"
        "</style></head>"
        f'<body style="background-color:{bg};color:{fg};margin:10px;">'
        f"{body}</body></html>"
    )


def build_webengine_html(md_text: str, shim, base_dir: Path) -> str:
    """完整 CSS 渲染（对齐生产预览模板观感，含 :root 变量与滚动条样式）。"""
    from src.editor.markdown_preview import (
        PREVIEW_HTML_TEMPLATE as _PREVIEW_HTML_TEMPLATE,
        _build_preview_css_vars,
    )

    body = render_markdown_to_safe_html(md_text)
    body = resolve_images(body, base_dir)
    body = process_code_blocks_web(body, shim)
    root_vars = _build_preview_css_vars(shim)
    return _PREVIEW_HTML_TEMPLATE.format(
        layout_css=MARKDOWN_LAYOUT_CSS,
        sb_width=10,
        sb_radius=5,
        sb_margin=3,
        content=body,
    )


# ════════════════════════════════════════════════════════
#  样例
# ════════════════════════════════════════════════════════

SAMPLES: list[tuple[str, str]] = [
    ("样例 1 · 文本结构", """# 一号标题 H1

这是**加粗**、*斜体*与 `inline code` 混合的段落，还有[外链 PanzerNote](https://github.com)和自动链接 https://qt.io。

## 二级标题 H2

> 引用块：观察 QTextDocument 的 border-left 与背景支持。
> 多行引用第二行，*引用内斜体*。

### 三级标题 H3

- 无序列表项一
- 无序列表项二
  - 嵌套项 A
  - 嵌套项 B

1. 有序列表一
2. 有序列表二

---

尾部段落：检查分割线与 h6 颜色。
###### 六级标题 H6
"""),
    ("样例 2 · 表格与任务", """## 表格与任务

| 列 A | 列 B | 列 C |
| ---- | ---- | ---- |
| 甲   | 1    | 是   |
| 乙   | 2    | 否   |
| 丙   | 3    | 是   |

- [x] 已完成任务
- [ ] 待办任务
- 普通列表项

表格下方段落，验证表格边框与表头底色。
"""),
    ("样例 3 · 代码块与图片", """## 代码块

```python
def hello(name: str) -> str:
    \"\"\"docstring 注释\"\"\"
    # 行注释
    items = [i * 2 for i in range(10)]
    print(f"hello {name}", items)
    return name.upper()
```

```javascript
const greet = (name) => {
  const items = [1, 2, 3].map(x => x * 2);
  console.log(`hello ${name}`, items);
  return name.toUpperCase();
};
```

## 本地图片

![秘书](data/assets/portraits/secretary.png)
"""),
]


# ════════════════════════════════════════════════════════
#  真实控件模式（A1 生产渲染路径）
# ════════════════════════════════════════════════════════

def run_integrated(args) -> int:
    """用真实 MarkdownPreviewWidget（生产 QTextBrowser 路径）出图。"""
    import tempfile

    from PyQt6.QtWidgets import (
        QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
    )

    from src.core.config import Config
    from src.editor.markdown_preview import MarkdownPreviewWidget
    from src.themes.theme_engine import ThemeEngine

    app = QApplication.instance() or QApplication(sys.argv)

    app_dir = tempfile.mkdtemp(prefix="pn_proto_integrated_")
    config = Config(app_dir=app_dir)
    theme_engine = ThemeEngine(config)
    theme_engine.initialize_active_theme()

    win = QWidget()
    win.setWindowTitle("A1 集成预览 · 真实 MarkdownPreviewWidget（QTextBrowser 路径）")
    layout = QVBoxLayout(win)
    widget = MarkdownPreviewWidget(config, theme_engine)
    layout.addWidget(widget, 1)

    controls = QHBoxLayout()
    state_label = QLabel("")
    btn_light = QPushButton("浅色主题")
    btn_dark = QPushButton("深色主题")
    btn_shot = QPushButton("保存截图")
    sample_btns = [QPushButton(name) for name, _ in SAMPLES]
    controls.addWidget(QLabel("样例:"))
    for b in sample_btns:
        controls.addWidget(b)
    controls.addSpacing(12)
    controls.addWidget(btn_light)
    controls.addWidget(btn_dark)
    controls.addWidget(btn_shot)
    controls.addStretch(1)
    controls.addWidget(state_label)
    layout.addLayout(controls)

    state = {"variant": args.variant, "sample_idx": args.sample - 1}
    theme_engine.theme_manager.request("default", args.variant)

    def _render() -> None:
        _, md_text = SAMPLES[state["sample_idx"]]
        widget.editor.setPlainText(md_text)
        widget.refresh_preview_now()
        state_label.setText(f"{SAMPLES[state['sample_idx']][0]} · {state['variant']}")

    def _set_variant(variant: str) -> None:
        state["variant"] = variant
        theme_engine.theme_manager.request("default", variant)
        widget._apply_theme_colors()
        _render()

    def _set_sample(idx: int) -> None:
        state["sample_idx"] = idx
        _render()

    btn_light.clicked.connect(lambda: _set_variant("light"))
    btn_dark.clicked.connect(lambda: _set_variant("dark"))
    for i, b in enumerate(sample_btns):
        b.clicked.connect(lambda _=False, idx=i: _set_sample(idx))

    def _save_shot() -> None:
        target = args.screenshot or "proto_integrated.png"
        win.grab().save(target)
        print(f"截图已保存: {target}")
        if args.screenshot:
            app.quit()

    btn_shot.clicked.connect(_save_shot)

    _render()
    win.resize(1000, 900)
    win.show()

    if args.screenshot:
        QTimer.singleShot(1500, _save_shot)

    return app.exec()


# ════════════════════════════════════════════════════════
#  对比窗口
# ════════════════════════════════════════════════════════

def main() -> int:
    from PyQt6.QtWidgets import (
        QApplication, QHBoxLayout, QLabel, QPushButton, QSplitter,
        QTextBrowser, QVBoxLayout, QWidget,
    )

    parser = argparse.ArgumentParser(description="A0 原型：QTextBrowser vs WebEngine 观感对比")
    parser.add_argument("--sample", type=int, default=1, choices=[1, 2, 3], help="初始样例序号")
    parser.add_argument("--screenshot", default="", help="渲染后自动截图保存路径（如 shot.png）")
    parser.add_argument("--no-webengine", action="store_true", help="禁用 WebEngine 左栏")
    parser.add_argument("--integrated", action="store_true",
                        help="使用真实 MarkdownPreviewWidget（A1 生产渲染路径）出图")
    parser.add_argument("--variant", default="light", choices=["light", "dark"],
                        help="--integrated 模式的初始主题")
    args = parser.parse_args()

    if args.integrated:
        return run_integrated(args)

    use_webengine = False
    WebEngineView = None
    if not args.no_webengine:
        try:
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
            from PyQt6.QtWebEngineWidgets import QWebEngineView

            use_webengine = True
            WebEngineView = QWebEngineView
        except ImportError:
            print("[WARN] PyQt6-WebEngine 不可用，左栏回退为占位说明")

    app = QApplication.instance() or QApplication(sys.argv)

    # ── 主题运行时 ──
    repo_root = Path(__file__).resolve().parents[1]
    themes_dir = repo_root / "themes"
    svc = ThemeV2Service(themes_dir)
    if not svc.load_default():
        print("ERROR: 主题 v2 加载失败")
        return 1
    mgr = ThemeManager(themes_dir, svc)
    shim = _ThemeShim(svc)
    mgr.request("default", "light")

    # ── 窗口 ──
    win = QWidget()
    win.setWindowTitle("A0 原型 · QTextBrowser(QTextDocument) vs WebEngine 观感对比")
    layout = QVBoxLayout(win)

    left = WebEngineView() if use_webengine else QLabel("WebEngine 不可用")
    right = QTextBrowser()
    if use_webengine:
        left.setMinimumWidth(420)
    right.setMinimumWidth(420)

    splitter = QSplitter()
    splitter.addWidget(left)
    splitter.addWidget(right)
    splitter.setSizes([700, 700])
    layout.addWidget(splitter, 1)

    # ── 底部控制栏 ──
    controls = QHBoxLayout()
    state_label = QLabel("")
    btn_light = QPushButton("浅色主题")
    btn_dark = QPushButton("深色主题")
    btn_shot = QPushButton("保存截图")
    sample_btns = [QPushButton(name) for name, _ in SAMPLES]
    controls.addWidget(QLabel("样例:"))
    for b in sample_btns:
        controls.addWidget(b)
    controls.addSpacing(12)
    controls.addWidget(btn_light)
    controls.addWidget(btn_dark)
    controls.addWidget(btn_shot)
    controls.addStretch(1)
    controls.addWidget(state_label)
    layout.addLayout(controls)

    state = {"variant": "light", "sample_idx": args.sample - 1}

    def _render() -> None:
        _, md_text = SAMPLES[state["sample_idx"]]
        qtext_html = build_qtext_html(md_text, shim, repo_root)
        right.setHtml(qtext_html)
        if use_webengine:
            web_html = build_webengine_html(md_text, shim, repo_root)
            left.setHtml(web_html)
        state_label.setText(
            f"{SAMPLES[state['sample_idx']][0]} · {state['variant']}"
            f" · WebEngine={'开' if use_webengine else '关'}"
        )

    def _set_variant(variant: str) -> None:
        state["variant"] = variant
        mgr.request("default", variant)
        _render()

    def _set_sample(idx: int) -> None:
        state["sample_idx"] = idx
        _render()

    btn_light.clicked.connect(lambda: _set_variant("light"))
    btn_dark.clicked.connect(lambda: _set_variant("dark"))
    for i, b in enumerate(sample_btns):
        b.clicked.connect(lambda _=False, idx=i: _set_sample(idx))

    def _save_shot(out: str | None = None) -> None:
        target = out or args.screenshot or "proto_shot.png"

        def _do_grab() -> None:
            win.grab().save(target)
            print(f"截图已保存: {target}")
            if args.screenshot:
                app.quit()

        # 等待渲染/布局稳定（WebEngine 异步渲染 + 富文本布局）再抓主窗口
        QTimer.singleShot(1500, _do_grab)

    btn_shot.clicked.connect(lambda: _save_shot())

    _render()
    win.resize(1500, 900)
    win.show()

    if args.screenshot:
        _save_shot()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
