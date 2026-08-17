# 主题 Token 映射表

> **⚠️ Wave8 Batch C（2026-08-17）后已过时**：v1 配色对象与 `themes/builtin/*.json`
> 已删除，颜色统一由 Theme v2 semantic token（`themes/default/variants/*.json`）承载。
> 本文件保留 v1 字段 → 使用位置的历史映射，作为收敛到 v2 token 的参考
> （收敛对照见 `Wave8-V1清理迁移方案.md` 第 2 节）。

---

## 通用颜色

| Token | 影响位置 |
|-------|---------|
| `primary` | QPushButton 背景、QSlider 滑块、快捷面板按钮、插件管理按钮、游戏侧栏选中边框（`theme_engine.py:generate_stylesheet`、`shortcut_panel.py`、`plugin_manager_dialog.py`、`game_sidebar.py`） |
| `primary_dark` | QPushButton:hover 背景、快捷面板按钮:hover、插件管理按钮:hover（`theme_engine.py`、`shortcut_panel.py`、`plugin_manager_dialog.py`） |
| `primary_light` | QMenu/QMenuBar::selected、QTreeView::selected、游戏侧栏选中、编辑器选中、文件树选中、命令面板选中、补全弹窗选中、行号区背景（`theme_engine.py`、`game_sidebar.py`、`editor.py`、`file_tree.py`、`command_palette.py`、`completion.py`） |
| `accent` | 侧栏活动按钮下划线（`side_panel_host.py`） |
| `accent_fg` | QPushButton 文字色、accent_fg 背景上的前景文字（`theme_engine.py` QSS 中 `color: white` 对应此语义） |
| `background` | QMainWindow 背景、Markdown 预览 fallback（`theme_engine.py`、`markdown_preview.py`） |
| `surface` | QMenu/QTabBar/QScrollBar 背景、命令面板/快捷键面板/插件管理/文件树/补全弹窗/查找替换栏/标签栏/游戏侧栏的非选中列表项（`theme_engine.py`、`command_palette.py`、`shortcut_panel.py`、`plugin_manager_dialog.py`、`file_tree.py`、`completion.py`、`find_replace.py`、`editor_tabs.py`、`game_sidebar.py`、`markdown_preview.py`） |
| `card` | QTabBar::selected 背景、QLineEdit 背景、命令面板输入框、补全弹窗主区域、插件管理输入框（`theme_engine.py`、`command_palette.py`、`completion.py`、`plugin_manager_dialog.py`） |
| `text_primary` | 全局默认文字色：QMainWindow/QMenuBar/QMenu/QTabBar/QLabel/QCheckBox/QGroupBox/QDialog/QTreeView（`theme_engine.py`）、编辑器文字（`editor.py`）、资源栏数值（`resource_bar.py`）、小秘书气泡文字（`secretary_widget.py`）、状态栏文字（`status_bar.py`）、命令面板/快捷键面板/补全弹窗/文件树/插件管理（各组件） |
| `text_secondary` | QStatusBar/QTabBar 非选中文字、QScrollBar:pressed、匹配计数标签、文件范围标签、资源栏文字、小秘书气泡文字（`theme_engine.py`、`find_replace.py`、`find_in_files_panel.py`、`resource_bar.py`、`secretary_widget.py`） |
| `text_disabled` | QScrollBar:hover、游戏占位符文字、侧栏返回按钮、补全弹窗滚动条、插件管理禁用按钮（`theme_engine.py`、`main_window.py`、`game_sidebar.py`、`completion.py`、`plugin_manager_dialog.py`） |
| `border` | 全局默认边框色：QMenuBar/QTabWidget/QTabBar/QLineEdit/QGroupBox/QSplitter/QScrollBar/QFrame/QStatusBar（`theme_engine.py`）、资源栏（`resource_bar.py`）、游戏侧栏（`game_sidebar.py`）、命令面板（`command_palette.py`）、补全弹窗（`completion.py`）、文件树（`file_tree.py`）、状态栏（`status_bar.py`）、侧栏（`side_panel_host.py`）、快捷键面板（`shortcut_panel.py`）、插件管理（`plugin_manager_dialog.py`）、Markdown 预览 TOC（`markdown_preview.py`）、主窗口分割线（`main_window.py`） |
| `divider` | 状态栏模块分隔符背景（`status_bar.py`） |
| `error` | 全局错误状态色（查找无结果输入框边框变红、编辑器错误标记等） |
| `warning` | 全局警告状态色（预留，当前未被 widget 显式引用） |
| `success` | 全局成功状态色（预留） |
| `info` | 全局信息状态色（预留） |

---

## 交互状态

| Token | 影响位置 |
|-------|---------|
| `hover_bg` | 标签栏关闭按钮:hover 背景（`editor_tabs.py`） |
| `active_bg` | QPushButton:pressed 背景（`theme_engine.py`） |
| `focus_border` | QLineEdit:focus 边框色（`theme_engine.py`）、查找替换栏输入框:focus（`find_replace.py`） |
| `selection_bg` | 预留（文本选区背景，当前 editor.py 使用 `primary_light`） |
| `selection_fg` | 预留（文本选区前景） |

---

## UI 区域颜色

| Token | 影响位置 |
|-------|---------|
| `sidebar_bg` | 文件树背景、侧栏面板宿主背景、游戏侧栏背景、编辑器行号区背景、行号区文字色（`file_tree.py`、`side_panel_host.py`、`game_sidebar.py`、`editor.py`） |
| `editor_bg` | 编辑器文本区背景（`editor.py`） |
| `editor_line_number` | 编辑器行号区文字色（`editor.py`） |
| `editor_current_line` | 编辑器当前行高亮背景（`editor.py`） |
| `editor_selection` | 文件树选中项背景、游戏侧栏当前页按钮背景、快捷键面板选中项（`file_tree.py`、`game_sidebar.py`、`shortcut_panel.py`） |
| `editor_bracket_match_bg` | 编辑器括号匹配高亮背景（`editor.py`） |
| `editor_bracket_match_fg` | 编辑器括号匹配高亮前景（`editor.py`） |
| `editor_bracket_unmatched` | 编辑器未匹配括号前景色（`editor.py`） |
| `minimap_bg` | 代码缩略图背景色（`minimap.py`） |
| `minimap_viewport` | 代码缩略图视口滑块色（`minimap.py`） |
| `statusbar_bg` | 状态栏和资源栏背景（`status_bar.py`、`resource_bar.py`） |
| `menubar_bg` | 菜单栏背景（`theme_engine.py`） |
| `dialog_bg` | 对话框背景、消息框背景（`theme_engine.py`）、快捷键面板对话框（`shortcut_panel.py`）、插件管理对话框（`plugin_manager_dialog.py`） |

---

## 编辑器专属

| Token | 影响位置 |
|-------|---------|
| `editor_bookmark_bg` | 编辑器书签槽背景色（`editor.py`） |
| `editor_bookmark_fg` | 编辑器书签槽文字色（`editor.py`） |
| `editor_fold_marker` | 编辑器折叠标记三角色 —— 展开状态（`editor.py`） |
| `editor_fold_marker_collapsed` | 编辑器折叠标记三角色 —— 折叠状态（`editor.py`） |

---

## 搜索

| Token | 影响位置 |
|-------|---------|
| `search_match_bg` | 查找命中高亮背景（`find_replace.py`） |
| `search_current_bg` | 当前查找命中高亮背景（`find_replace.py`） |
| `search_current_fg` | 当前查找命中高亮前景（`find_replace.py`） |

---

## 资源与游戏

| Token | 影响位置 |
|-------|---------|
| `resource_fuel` | 资源栏燃料图标色（`resource_bar.py`） |
| `resource_ammo` | 资源栏弹药图标色（`resource_bar.py`） |
| `resource_steel` | 资源栏钢材图标色（`resource_bar.py`） |
| `resource_bauxite` | 资源栏铝材图标色（`resource_bar.py`） |
| `game_build` | 游戏侧栏建造图标色（`game_sidebar.py`） |
| `game_garage` | 游戏侧栏车库图标色（`game_sidebar.py`） |
| `game_collection` | 游戏侧栏图鉴图标色（`game_sidebar.py`） |
| `secretary_bubble_bg` | 小秘书气泡背景（`secretary_widget.py`） |
| `secretary_bubble_border` | 小秘书气泡边框（`secretary_widget.py`） |

---

## 代码块

| Token | 影响位置 |
|-------|---------|
| `bg_codeblock` | Markdown 预览代码块 fallback 背景（`markdown_preview.py`）、安全渲染代码块背景（`secure_markdown_renderer.py`） |
| `codeblock_border` | Markdown 预览代码块 fallback 边框（`markdown_preview.py`） |

---

## Markdown 编辑器高亮

> 所有 `md_*` token 通过 `syntax_highlighter.py` 的 `MarkdownHighlighter` 作用于编辑器内 Markdown 语法高亮。

| Token | 影响位置 |
|-------|---------|
| `md_h1_fg` | 编辑器 — Markdown H1 标题前景色（`syntax_highlighter.py`） |
| `md_h2_fg` | 编辑器 — Markdown H2 标题前景色 |
| `md_h3_fg` | 编辑器 — Markdown H3 标题前景色 |
| `md_h456_fg` | 编辑器 — Markdown H4/H5/H6 标题前景色 |
| `md_bold_fg` | 编辑器 — Markdown 粗体前景色 |
| `md_italic_fg` | 编辑器 — Markdown 斜体前景色 |
| `md_code_fg` | 编辑器 — Markdown 行内代码前景色 |
| `md_code_bg` | 编辑器 — Markdown 行内代码背景色 |
| `md_link_fg` | 编辑器 — Markdown 链接前景色 |
| `md_image_fg` | 编辑器 — Markdown 图片语法前景色 |
| `md_list_fg` | 编辑器 — Markdown 列表标记前景色 |
| `md_quote_fg` | 编辑器 — Markdown 引用块前景色 |
| `md_hr_fg` | 编辑器 — Markdown 分隔线前景色 |
| `md_fence_fg` | 编辑器 — Markdown 代码围栏标记前景色 |
| `md_code_block_fg` | 编辑器 — Markdown 代码块文字前景色 |
| `md_code_block_bg` | 编辑器 — Markdown 代码块背景色 |

---

## 语法高亮（Pygments）

> 所有 `syntax_*` token 通过 `highlight_themes.py` 的 `TOKEN_MAP` 映射到 Pygments Token。
> 同时作用于编辑器代码高亮和 Markdown 预览中的代码块高亮。

### 关键字

| Token | 映射的 Pygments Token |
|-------|----------------------|
| `syntax_keyword` | `Token.Keyword`、`Token.Keyword.Constant`、`Token.Keyword.Declaration`、`Token.Keyword.Namespace`、`Token.Keyword.Pseudo`、`Token.Keyword.Reserved`、`Token.Generic.Prompt` |
| `syntax_keyword_type` | `Token.Keyword.Type` |

### 名称

| Token | 映射的 Pygments Token |
|-------|----------------------|
| `syntax_builtin` | `Token.Name.Builtin`、`Token.Name.Builtin.Pseudo` |
| `syntax_class` | `Token.Name.Class`、`Token.Name.Exception` |
| `syntax_function` | `Token.Name.Function`、`Token.Name.Function.Magic`、`Token.Name.Decorator` |
| `syntax_variable` | `Token.Name.Variable`、`Token.Name.Attribute`、`Token.Name.Constant`、`Token.Name.Other`、`Token.Name.Entity` |
| `syntax_tag` | `Token.Name.Tag` |
| `syntax_namespace` | `Token.Name.Namespace`、`Token.Name.Label` |

### 字面量

| Token | 映射的 Pygments Token |
|-------|----------------------|
| `syntax_string` | `Token.Literal.String`（及所有子类型：Single/Double/Other/Backtick/Char/Symbol/Regex/Heredoc） |
| `syntax_string_escape` | `Token.Literal.String.Escape` |
| `syntax_string_affix` | `Token.Literal.String.Affix`、`Token.Literal.String.Interpol` |
| `syntax_string_doc` | `Token.Literal.String.Doc` |
| `syntax_number` | `Token.Literal.Number`（及所有子类型：Integer/Float/Oct/Hex/Bin） |

### 其他

| Token | 映射的 Pygments Token |
|-------|----------------------|
| `syntax_comment` | `Token.Comment`（及所有子类型：Single/Multiline/Special） |
| `syntax_operator` | `Token.Operator`（及所有子类型：Word/Math/Comparison） |
| `syntax_punctuation` | `Token.Punctuation` |
| `syntax_text` | `Token.Text`、`Token.Text.Whitespace` |
| `syntax_error` | `Token.Error`、`Token.Generic.Error` |
| `syntax_deleted` | `Token.Generic.Deleted` |
| `syntax_inserted` | `Token.Generic.Inserted` |
| `syntax_heading` | `Token.Generic.Heading`、`Token.Generic.Subheading` |
| `syntax_output` | `Token.Generic.Output`、`Token.Generic.Traceback`、`Token.Generic.Emph`、`Token.Generic.Strong` |
