# Changelog

本文件记录 PanzerNote 各版本的变更。版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范。

## v1.9.0

**分屏功能修复（3.5.1~3.5.12）**

- **布局方向对称（3.5.1）**：`split_editor` 水平/垂直方向 `setSizes` 基准尺寸对称
- **分屏状态持久化（3.5.2）**：workspace.json 记录分屏布局与激活标签，重启恢复布局与文件；临时会话纳入分屏（内容不丢）
- **打开/新建焦点感知（3.5.3）**：`FileActionController` 目标面板改为构造注入的 Callable 提供者（焦点感知），打开/新建文件进入当前聚焦的分屏而非固定主面板
- **标签跨分屏拖拽迁移（3.5.4）**：标签可在分屏间拖拽迁移，`tab_id`/`TabState`/脏标记随标签转移不丢失；迁移后编辑器信号重绑
- **分屏方向切换（3.5.6）**：按方向记忆分割比例，切换方向沿用该方向上次占比
- **统一未保存关闭确认（3.5.7）**：新增 `ui/unsaved_files_dialog.py`（VS Code 风格单级确认，1 个→单文件样式、多个→汇总样式）；关闭分屏与退出程序统一走确认；保存并关闭遍历各面板 `save_all_for_close()`，任一另存为取消/提交失败中止关闭，全部提交后异步等待各面板保存任务完成
- **拖放文件按释放位置路由**：`dropEvent` 按释放点落在哪个面板矩形内决定打开目标（拖拽期间焦点在文件树上，焦点追踪会回退到"最近聚焦面板"），释放点不在任何面板内则回退焦点面板
- **空分屏自动关闭与空会话兜底（3.5.9）**：分屏标签全关自动关闭分屏；主面板标签全关自动新建未命名标签（总有可编辑位置）；新增「重置分屏布局」菜单项；`tab_count_changed` 改带参数，主面板与分屏复用同一处理器（移除 event_bus 重复连接）
- **未命名文件持久化恢复（3.5.10）**：未命名标签随会话持久化（workspace.json 存编号/显示名，dirty 时附带内容），重启后还原标签与编辑现场（沿用原编号，无 IO 开销）
- **未命名标签拖拽（3.5.11）**：新增 `MIME_TAB_ID`，未命名标签也可跨分屏迁移与拖到文件树落盘保存；未命名编号随标签迁移（源释放/目标占用），避免编号冲突；空 MIME 数据格式在平台拖拽协议中被丢弃导致落盘失败的兼容处理
- **文件树拖拽修复（3.5.11）**：PyQt6 拖拽事件仅 `position()`（QPointF），改用 `position().toPoint()`；`QFileSystemModel` 默认 `readOnly` 导致 `dropMimeData` 失败，改为 `setReadOnly(False)+setDragEnabled(True)+NoEditTriggers`；标签拖到文件树由静默移动升级为异步移动/复制/取消询问（新增 `copy_file_to_folder`）
- **文件树删除同步关标签（3.5.11）**：`FileTreeWidget` 新增 `file_deleted` 信号，删除成功后同步关闭匹配路径的打开标签（已修改弹确认「关闭并放弃修改」，不提供保存以免把已删除文件重建回来），并清理 autosave
- **标签 tooltip 路径区分（3.5.12）**：tooltip 区分已保存（完整路径）与未保存（「未保存」），迁移/打开/保存后统一刷新；主题样式表补充 QToolTip 段落

**共享文档多视图（3.5.8，跨面板联动编辑）**

- **核心模型**：新增 `core/shared_document.py`（`SharedDocument` 真正拥有 `QTextDocument`，`Document` = 内容与持久化状态；`ViewState` 每 View 独立 cursor/scroll 快照）、`core/document_registry.py`（`document_id`/路径索引/View 关联/生命周期）、`core/document_view_binding.py`（View↔Document 信号接线器，attach/detach 幂等）
- **自动共享**：另一面板已打开同一文件 → 不重新读盘，直接新建 View attach 到共享 Document（内容/编码/eol 单一源）
- **关闭决策树**：非最后一个 View 关闭直接关（不弹确认、不销毁 Document、不动未命名编号）；最后一个 View 关闭才走 dirty 确认 → release 销毁
- **Save As re-key**：另存为成功后 `document_id` 不变、路径更新；目标路径已被其它 Document 占用 → 拒绝（不允许两个 Document 指向同一路径）
- **迁移合并**：标签跨面板迁移合并到共享 View（同 Document 不重复创建）；autosave 按 Document 一份
- **保存竞态防护**：`SaveTaskManager` 两维度改造（dirty × save_status 状态机）+ 单槽合并保存（IDLE/SAVING/FAILED），多 View 防并发写盘；保存任务按 Document 合并
- **折叠/书签收敛 Document 级**：折叠状态与书签随 Document 共享（规格 2.10/2.12）
- **信号按 View 接入**：`DocumentViewBinding` 每 View 一个（dirtyChanged → 标题脏标记；nameChanged → 标题跟随；pathChanged → TabState 路径 + Markdown 预览 base_path 跟随），关闭/迁移即断，无 UniqueConnection 残留
- **ViewState 接线**：每 View 独立 `view_state`，关闭时写入 cursor/scroll 快照，重启恢复
- **共享高亮与主题切换**：共享 `QTextDocument`；两种高亮器均实现 `set_dark_mode`（主题切换不再经过 `set_file_type` 重建，避免摘除共享高亮）；关闭最后 View 前断开 Document 依赖，杜绝 C++ deleted 悬垂崩溃
- **文件移动 re-key**：文件树移动共享文件后路径索引换键 + `bind_path` 广播，所有 View 的路径/标题随 Document 同步（保存不再写回旧文件）
- **未保存跨面板去重**：退出确认框按 `document_id` 去重，同一共享文件只列一次
- **依赖声明**：`shiboken6` 显式写入 `requirements.txt`

**收尾修复（跨面板保存安全）**

- **跨面板并发写盘防护**：共享 Document 以 Document 级保存状态机（`request_save`/`on_save_succeeded`/`on_save_failed`）为跨面板唯一门闩——主面板与分屏的 `SaveTaskManager` 相互独立，`document_key` 合并仅面板内有效，接线后同一 Document 全局同时最多一个实际写盘任务，最新内容必然最后落盘；保存期间编辑 + 再次请求自动补保存；门闩直接连 `SaveTask.signals.finished` 释放（标签已注销也不卡死 SAVING）
- **safe_write 原子化**：同目录临时文件（`.pn_tmp_*` 前缀便于识别残留）+ `os.replace` 原子替换——写入中途崩溃/断电不留下半写文件，并发写目标始终是完整版本（last-write-wins）；失败时清理临时文件并重新抛出；保留原文件权限；`safe_write`/`safe_write_bytes` 统一走 `_atomic_write`

## v1.8.5

**Wave 3 主窗口职责拆分收尾（A~E 分支）**

**控制器抽取**

- **EditActionController**：新增 `editor/edit_action_controller.py`，承载 22 个编辑动作（撤销/剪贴板/查找/行操作/大小写/书签/折叠），MainWindow 保留一行委托
- **ExportActionController**：新增 `editor/export_action_controller.py`，承载导出编排；HTML 导出统一走 FileGuard 安全写入（`safe_write` + FileAccessContext），file_guard 设为必填参数防绕过
- **SettingsActionController**：新增 `editor/settings_action_controller.py`，承载设置动作编排（对话框应用/导出/导入/保存/重置）；`_apply_editor_dict` 供 show 与 apply 共享消除重复；wrap 菜单同步收敛为 `_sync_wrap_menu`（消除三处重复）
- **ViewCoordinator**：新增 `ui/view_coordinator.py`，承载视图/分屏/面板切换（`_current_view`/`_split_tabs` 状态迁移）；依赖全构造注入，信号连接/菜单同步回调由 MainWindow 注入

**UI 组装与事件过滤**

- **MainWindowUIBuilder**：新增 `ui/main_window_ui.py`，承载顶层 widget 创建与布局（17 个组件经 `BuiltUI` 返回），builder 内不连接业务信号（回应 hotfix.txt 信号集中连接约束）
- **SelectionClearFilter**：`_SelectionClearFilter` 独立为 `ui/selection_clear_filter.py`（纯移动，行为不变）

**保存与导出修复**

- **另存为副本语义**：另存为不再改变原标签显示名；支持另存为 PDF
- **HTML 另存为**：.html/.htm 另存为渲染为可打开的 HTML 网页
- **导出统一走 FileGuard 安全写入**：HTML 导出与 PDF 导出（含 PDF 另存为）均经 `safe_write_bytes`，遵守路径白名单与文件大小限制
- **自动保存（autosave）安全写入**：临时会话 autosave 写入/读取统一经 FileGuard（路径白名单/大小限制/超时），`TempSessionManager` 构造注入 `file_guard`
- **分屏保存焦点感知**：Ctrl+S 保存路由到当前焦点所在分栏（`_focused_editor_tabs`），修复分屏后保存错位
- **会话滚动恢复兜底**：首帧布局未完成时 `setValue` 被 clamp，改用 rangeChanged 等滚动范围就绪后重试一次再断开
- **分栏占比持久化**：编辑区/Markdown 预览分栏占比保存与恢复

**架构文档**

- `docs/architecture.md`：职责表补充 6 个新增模块，记录行数基线（main_window.py 1669 → 1255）

## v1.8.4

**文件树选中高亮交互修复**

- **点击空白区域清除选中高亮**：`MainWindow` 安装应用级事件过滤器 `_SelectionClearFilter`，点击视窗内任何项目视图（`QAbstractItemView`，含文件树/大纲等）之外区域时，清空全部子视图选中态与 `currentIndex`，选中高亮蓝色块在跳出列表区域时消失
- **范围内点击行为保持不变**：点击落在项目视图可视矩形内时交由 Qt 内部 `selectionModel` 处理，原有切换选中项 / Ctrl / Shift 多选逻辑不受影响
- **场景覆盖**：坐标获取优先使用 `globalPosition()`，兼容应用级事件过滤；模态对话框弹出时不干扰其内部列表；跨窗口点击不误操作；文件树空白点击清除选中的局部处理保留
- **mypy 类型修复**：`main_window.py` 修复 5 个错误（`eventFilter` 签名对齐父类 `Optional` 参数、`QMouseEvent` 类型收窄、`model()` 局部变量化、`QApplication.instance()` 空值守卫）；`editor_tabs.py` 修复 4 个错误（`result` 显式 `Dict[str, object]`、`document()` 空值守卫、`clearUndoRedoStacks()` 移至 `QTextDocument`）。`mypy src/` 86 个文件零错误

**Wave 3/4 配置与职责重构（hotfix 阶段 0-7）**

- **Config 拆分**：Config 由配置中枢演进为门面（Facade），内部委托 PathResolver（base_path / user_data_path.txt / 目录 getter + JSON 工具）、SettingsStore（settings dict / 命名空间设置 / reset_to_defaults）、WorkspaceStore（workspace dict / 会话状态 / 书签 / 折叠 / 关闭标签记忆）。对外保持 v1.6.x 起完整接口，调用方零改动；main_window 移除 4 处 config 私有成员访问
- **类型化文档模型**：新增 `core/document_model.py`（TabState + TabStateRegistry），替代无类型 `_tab_info` dict；保存状态副作用集中到 TabState（`_on_save_state_changed` CLEAN 分支统一处理 `mark_saved` / `mark_new_saved`）
- **会话恢复服务化**：新增 `core/session_restore_service.py`，将分级恢复计划（pre_show / deferred）、光标/滚动位置恢复、崩溃恢复（`check_crash_recovery` / `restore_after_crash`）从 MainWindow 提取为独立服务，MainWindow 仅保留调用与 UI 提示
- **文件打开编排**：新增 `editor/file_action_controller.py`，集中文件打开编排（安全校验 → 外部文件注册 → 最近文件过滤并持久化），错误弹窗/文件树刷新/菜单构建等 UI 副作用保留在 MainWindow
- **应用上下文**：新增 `core/app_context.py`（AppContext），main.py 创建并传入 MainWindow；服务层经 app_context 直连子模块，Config 门面过渡期共存，新代码鼓励直连子模块
- **存档防泄漏**：SavegameManager 通过 MappingProxyType 暴露只读存档视图、get_resources 返回拷贝；新增字段级 API（get_savegame_field / set_savegame_field），消除整档引用透传

**会话与崩溃可靠性**

- **关闭标签页位置记忆**：关闭标签时持久化光标/滚动位置到 workspace.json（closed_tabs_memory），重新打开时恢复并清除；Ctrl+Shift+T 内存栈限 50 条
- **崩溃日志误报修复**：正常退出时清空 crash\_\*.log（异常退出由 excepthook 写日志后直接终止进程，不会触发清理），消除"上次启动异常退出"的历史残留误报

**代码质量与类型**

- **数据防泄漏**：SettingsStore.as_dict() / WorkspaceStore.as_dict() 改返回深拷贝，杜绝调用方绕过封装修改内部状态；migrate_bauxite_counter 迁移改显式 API
- **白名单单一来源**：workspace 字段白名单由 DEFAULT_WORKSPACE 派生，ConfigImportService 直接复用，消除两份白名单漂移（配置导入时书签/折叠/关闭标签记忆不再被丢弃）
- **类型清理**：消除 3 处 Returning Any 与裸泛型，file_action_controller.open_file 返回类型统一为 int，main.py 提取 \_iter_crash_logs 消除 4 处 crash 日志枚举重复

## v1.8.3

**Wave 1 主题迁移：语法高亮并入语义 token、内置主题 JSON 化**

**语法高亮颜色并入 ThemeColorScheme**

- **24 个 `syntax_*` token**：新增 keyword/keyword_type/builtin/class/function/variable/tag/namespace/string/string_escape/string_affix/string_doc/number/comment/operator/punctuation/text/error/deleted/inserted/heading/output 等语法高亮颜色 token，默认值为 PyCharm Light 色值
- **TOKEN_MAP 替换 THEMES 字典**：`highlight_themes.py` 删除约 200 行硬编码 `THEMES` 字典，改为 60+ 条 `{Pygments Token → syntax_* 属性名}` 映射表。所有签名从 `theme_name: str` 改为 `theme_engine`
- **粗体/斜体装饰集中管理**：新增 `_TOKEN_BOLD` 和 `_TOKEN_ITALIC` frozenset，统一管理跨主题的粗体/斜体装饰（基于 PyCharm Light 装饰规则，暗色主题复用）
- **调用方更新**：`syntax_highlighter.py`、`editor.py`、`markdown_preview.py`、`async_highlight.py` 全部接入 theme_engine 对象

**内置主题迁移到 JSON 文件**

- **新建 `themes/builtin/light.json`**：68 个 color token，浅色主题零硬编码
- **新建 `themes/builtin/vscode_dark.json`**：94 个 color token，深色主题零硬编码，对标 VS Code Dark Modern 配色
- **加载机制**：`_load_builtin_themes()` 改为扫描 `themes/builtin/` 目录，自动加载所有 JSON 主题文件
- 所有颜色变更只需编辑 JSON 文件，无需修改 Python 代码

**主题管理界面完善**

- 主题预览从 4 个分组 35 个 token 扩展为 11 个分组 91 个 token（100% 覆盖）
- 新增分组：交互状态 / 搜索高亮 / 书签与折叠 / 代码块 / 游戏图标 / Markdown 高亮 / 语法高亮
- 新增 `themes/token_mapping.md`：每个 token 的代码位置与影响范围速查表

**未使用 token 清理与接线**

- 删除 9 个从未使用的 token（4 个接入实际位置：`accent` → 侧栏、`secretary_bubble_border` → 小秘书、`active_bg` → QPushButton:pressed、`focus_border` → QLineEdit:focus）
- 确认 16 个 `md_*` token 正被编辑器 Markdown 语法高亮使用，予以保留

**兼容性说明**

- `highlight_themes.py` 公共 API 签名变更：`get_editor_formats(theme_name)` → `get_editor_formats(theme_engine)`；`highlight_code_html(code, language, theme_name)` → `highlight_code_html(code, language, theme_engine)`。所有调用方已同步更新
- 用户自定义 `theme.json` 中若缺少新增的 `syntax_*` 或 `md_*` token，`ThemeColorScheme.from_dict()` 自动回退到 dataclass 默认值

## v1.8.2

**Markdown 预览代码块复制功能迁移至 QWebEngineView**

- **代码块一键复制补全**：将代码块复制功能从 QTextBrowser 降级引擎（`PreviewBrowser`）迁移至 QWebEngineView 主力引擎。HTML 模板中嵌入浮动复制按钮，CSS 实现悬停显隐，半透明色兼容明暗主题
- **document.title 桥接模式**：JS 事件委托捕获复制点击，通过 `document.title = '__pncopy__:N'` 回传 Python 侧，`_on_preview_title()` 新增 `__pncopy__` 分支调用 `QApplication.clipboard().setText()` 执行复制，绕过 Chromium 非安全上下文剪贴板限制
- **复制反馈**：点击后按钮显示 ✓ 符号，800ms 后恢复 📋
- **降级路径保留**：`PreviewBrowser`（QTextBrowser）原有的 QPushButton 复制实现完整保留，不受影响

**移除存档加密系统**

- **SavegameManager 简化为纯明文存档管理器**：移除 `CryptoManager`、`_encryption_password`、`_encrypted_unread` 等全部加密状态与逻辑。`SavegameSaveResult` 枚举从三个值（`SUCCESS`/`SKIPPED_ENCRYPTED_UNREAD`/`ENCRYPTION_FAILED`）简化为两个（`SUCCESS`/`WRITE_FAILED`）。`load()` 不再检测 `.encrypted` 文件，直接加载 `savegame.json`；`save()` 改为 try/except 包裹，失败时返回 `WRITE_FAILED`
- **Config 删除加密依赖**：移除 `CryptoManager` 的导入与实例化，`SavegameManager` 不再接收 `crypto_manager` 参数。删除 `is_savegame_encrypted()`、`set_encryption_password()` 等 6 个加密代理方法
- **MainWindow 删除加密弹窗**：删除 `_prompt_encrypted_savegame_save()` 整个方法。`_save_state()` 中 `SavegameSaveResult` 仅处理 `WRITE_FAILED`，弹窗提示检查磁盘空间或文件权限
- **删除文件与清理依赖**：删除 `src/security/crypto_manager.py`（含 `CryptoManager`、`DecryptionError`、`MigrationError` 类），更新 `__init__.py` 导出。移除 `requirements.txt` 和 `pyproject.toml` 中的 `cryptography>=48.0.0` 依赖
- **幽灵 API 清理**：`plugin_api_views.py` 的 `_DENIED_ATTRS` 中移除已不存在的 `set_encryption_password`、`enable_encryption`、`disable_encryption`
- **文档同步**：README 特性概览和安全与限制章节移除存档加密相关描述；architecture.md 删除 `crypto_manager.py` 目录条目、4.11.4 整节及相关安全约束条目

**兼容性说明**

- 本次变更为破坏性变更。
- `SavegameSaveResult` 枚举值变更：`SKIPPED_ENCRYPTED_UNREAD` 和 `ENCRYPTION_FAILED` 已移除，新增 `WRITE_FAILED`

## v1.8.1

**启动性能与窗口显示优化**

**窗口显示入口统一**

- **集中式 `present()` 入口**：`MainWindow` 新增 `present()` 作为唯一窗口显示入口，替代直接 `show()`。`__init__()` 期间窗口始终不可见，首个同步恢复文件在显示前完成控件挂载
- **最大化启动预缩放**：新增 `_restore_window_geometry()`，最大化场景在窗口不可见时预缩放控件树到屏幕可用尺寸并设置 `WindowMaximized` 状态，使 `showMaximized()` 首帧 paint 时 backing store 已是正确尺寸，消除普通尺寸→最大化尺寸的两段式视觉撕裂
- **mypy 全量类型修复**：`main_window.py`、`editor.py`、`folding.py`、`completion.py`、`plugin_manager_dialog.py`、`shortcut_panel.py`、`side_panel_host.py`、`window_theme.py` 中的 `QApplication.instance()` 调用改为 `cast(QApplication, ...)`，viewport/signalsBlocked 等处补充 `type: ignore` 注解；`window_theme.py` 的 `eventFilter` 签名补充 `None` 守卫

**会话恢复策略优化**

- **分级恢复计划**：新增 `_build_restore_plan(open_files)`，将打开文件列表拆分为 `pre_show_entries`（首个标签 + 首个 Markdown 标签，显示前同步挂载）和 `deferred_entries`（其余文件，显示后通过 `QTimer.singleShot(0, ...)` 异步恢复）。若首个标签和首个 Markdown 是同一文件，只恢复一次
- **光标恢复提取**：新增 `_restore_cursor_for_tab(file_info, tab_index)`，支持 `Editor` 和 `MarkdownPreviewWidget` 的光标位置/滚动位置恢复，被 pre-show 和 deferred 两条路径复用

**WebEngine 启动锚点机制**

- **启动锚点预初始化**：新增 `src/editor/webengine_runtime.py`（`WebEngineRuntime`），在主窗口 `__init__` 中创建，布局 setup 期间调用 `prepare_startup_anchor()` 在编辑器容器中挂载 1×1 最小 QWebEngineView，强制 Qt WebEngine 提前加载 Chromium 运行时，消除首个 Markdown 预览打开时的白屏卡顿
- **锚点释放**：`MarkdownPreviewWidget` 首个真实 QWebEngineView 预览挂载到控件树后，调用 `notify_real_view_attached()` 延迟释放启动锚点，回收占用的 GPU 资源
- **全链路注入**：`WebEngineRuntime` 实例通过 `MainWindow` → `EditorTabWidget` → `MarkdownPreviewWidget` 逐级传递

**非活动预览延迟渲染**

- **延迟渲染标志**：`MarkdownPreviewWidget` 新增 `_preview_dirty` / `_initial_preview_rendered` 标志。`open_file(render_preview=False)` 打开的 Markdown 标签跳过预览渲染，仅创建编辑器控件
- **按需激活渲染**：新增 `invalidate_preview()`（标记预览为脏）和 `ensure_preview_rendered()`（仅在 `_preview_dirty` 时触发渲染，避免重复计算）。选项卡切换时调用 `ensure_preview_rendered()`，确保切换到后台 Markdown 标签时预览即时就绪
- **启动加速**：会话恢复时首个标签以外的 Markdown 文件均以 `render_preview=False` 打开，在窗口显示后再按需渲染，减少启动阻塞

## v1.8.0

**编辑器能力增强、Markdown 预览稳定化与深色主题系统补全**

**编辑器基础能力增强**

- **缩进配置**：支持 `indent_size` / `use_tabs` 配置，统一缩进行为，消除多处硬编码缩进值
- **行尾配置**：打开文件时探测 LF/CRLF，保存时按配置规范化，状态栏可点击切换行尾格式
- **中文友好字数统计**：CJK 按单字计数，拉丁文本按词计数
- **括号匹配高亮**：新增括号对高亮，接入主题颜色
- **书签持久化**：书签保存到 `workspace.json`，关闭重开后恢复
- **快捷键统一管理**：快捷键逐步收敛到 ShortcutManager，减少 editor 内部硬编码

**工作流与导航能力增强**

- **Markdown 大纲导航面板**：解析 Markdown 标题，支持跳转，根据当前文件类型显隐
- **命令面板**：支持 `Ctrl+Shift+P` / `F1` 打开，搜索命令、执行命令，位置记忆
- **侧栏面板宿主**：统一管理文件树、大纲等侧边面板，活动栏按钮切换，支持宽度记忆
- **跨文件搜索**：后台线程遍历文件，按文件分组展示结果，双击跳转
- **文档缓冲区自动补全**：基于当前文档词频和大小写精确匹配排序，支持 `Enter`/`Tab` 接受、`Esc` 关闭，IME 组字期间不弹出

**Markdown 标题折叠与预览折叠同步**

- **标题折叠**：支持标题层级折叠、嵌套折叠恢复
- **工作区持久化折叠状态**：折叠状态持久化到工作区文件，关闭重开后恢复
- **Minimap 跳过隐藏 block**：缩略图跳过折叠区域的渲染
- **跳转自动展开**：大纲导航跳转时自动展开目标区块
- **预览面板折叠同步**：编辑区折叠状态通过 `fold_state_changed` 同步到右侧 HTML 预览
- **折叠后预览滚动回授锁**：避免 DOM 变化后预览滚动反向干扰编辑器

**Markdown 预览首次渲染稳定化**

- 新增 `refresh_preview_now()`，Markdown 文件加载完成后显式刷新预览，不再依赖 `textChanged` 防抖触发，提高首次打开/切换 Markdown 文件时的预览确定性

**深色主题系统补全**

- **Windows 原生标题栏深色**：抽出 `window_theme.py`，对主窗口和顶层窗口统一应用 DWM 深色标题栏，深色模式重启后标题栏不再变白
- **启动期间弹窗修复**：文档加载时停止补全定时器并隐藏弹窗，编辑器隐藏/失焦时也隐藏弹窗
- **弹窗深色化**：补齐主题管理（ThemePreviewDialog）、插件管理（PluginManagerDialog）、快捷键面板、自动补全弹窗（CompletionPopup）、标签栏（EditorTabWidget）等区域的深色样式，解决多处白底、浅字、标题栏不跟随主题的问题

**Markdown 代码块配色优化**

- **编辑区**：暗色代码块背景增强层次对比，fence 行颜色增强，解决 fenced code block 边界不明显的问题
- **预览区**：代码块增加边框和暗色背景层级（`#2D2D30`），深色主题下默认使用 VS Code 风格代码高亮，避免历史浅色高亮配置污染深色预览

**Markdown 预览模板安全网**

- `PREVIEW_HTML_TEMPLATE.format()` 异常时记录日志并回退到极简安全 HTML，避免模板花括号错误导致预览全空白

**颜色审计**

- 新增 `docs/color_audit.md`，记录硬编码颜色审计结果和后续迁移计划

## v1.7.0

**Markdown 预览滚动同步改造**

- **源码行号同步替代百分比同步**：将 Markdown 预览同步方式从"滚动条百分比同步"改为"源码行号到预览 DOM 锚点同步"。编辑器滚动时获取当前顶部源码行号，通过 JS 查找预览 HTML 中最接近的 `data-source-line` 节点并滚动到对应位置
- **源码行号注入渲染**：新增 `_render_markdown_with_source_map()` 方法，使用 markdown-it-py 的 `token.map` 给块级 HTML 节点注入 `data-source-line` 属性，覆盖标题、段落、引用、列表、表格、代码块、分割线等 token 类型
- **代码块源码行号保留**：`_build_container()` 和 `_process_code_blocks()` 支持传入 `source_line` 参数，代码块外层容器携带 `data-source-line` 属性，确保代码块区域也能精准同步
- **JS 插值同步算法**：HTML 模板注入 `scrollToSourceLine()` 函数，在相邻两个锚点节点之间做线性插值，改善长表格、长列表、长代码块的同步体验
- **图片加载后重同步**：HTML 模板注入 `resyncAfterImagesLoaded()` 函数，图片加载完成或失败后自动重新同步预览位置，避免图片撑开页面导致错位
- **QTextBrowser fallback 保留**：QWebEngineView 使用源码行号同步，QTextBrowser 继续使用旧百分比同步（无 DOM 查询能力）

## v1.6.6

**性能优化、安全加固与Bug修复**

- **自动配对性能优化**（A.1）：重构 `auto_pair_handler.py`，引入 `frozenset` 快速过滤机制，非括号/引号字符 O(1) 返回，不再读取光标或全文；新增 `_doc_char_at()` 按需访问文档单字符，替代 `toPlainText()` 全文复制；新增 `_ensure_auto_pair_cache()` 惰性加载字符集缓存，仅在 `AUTO_PAIR_CHARS` 变更时重建；`_pick_single_cjk_quote` 改用 `QTextCursor` 读取前缀，替代 `toPlainText()` + 切片；行内引号计数改用 `block.text()` + `str.count(start, end)`，替代全文切片
- **选区包裹优化**（A.2）：新增 `_wrap_selection()` 方法，使用 `QTextCursor` 操作包裹选区，避免 `selectedText()` 大字符串复制。4处调用点统一使用新方法
- **MarkdownIt 实例复用**（B.1/PERF-002）：`MarkdownPreviewWidget` 新增 `_create_md_parser()` 方法，在 `__init__` 中创建一次 MarkdownIt 解析器实例并缓存为 `_md_parser`，`_render_markdown()` 直接调用缓存的实例渲染，消除每次按键重复实例化 + 插件注册的开销（每次渲染节省 5-7ms，约 30-50% 提升）。deflist 插件 ImportError 增加 debug 日志
- **文件保存异步化**（B.2/PERF-003）：新建 `src/editor/save_task.py`（`SaveTask` + `SaveTaskSignals`），将 `safe_write` 磁盘 IO 放到 `QThreadPool` 后台线程执行。`EditorTabWidget._save_file()` 改为异步保存：主线程仍需 `toPlainText()` 获取内容，但磁盘写入在后台完成，UI 不再因大文件保存冻结。`save_all_to_temp()` 同步改为异步。保存失败时自动回滚修改状态并恢复标签页 `*` 标记
- **Markdown 预览增量更新**（B.3/PERF-007）：`PREVIEW_HTML_TEMPLATE` 新增 `<div id="content">` 包裹内容区。`MarkdownPreviewWidget` 新增 `_html_template_loaded` 标志，首次渲染走 `setHtml` 加载完整模板，后续渲染通过 `QWebEngineView.runJavaScript()` 仅更新 `innerHTML`，避免每次重建整个 DOM 树。切换文档（`base_path` 变化）时自动重置标志。`loadFinished` 信号触发后标记模板已加载
- **Minimap 块级缓存增量失效**（B.4/PERF-004）：`MinimapWidget` 改用 `QTextDocument.contentsChange` 信号（带 `from_pos/chars_removed/chars_added` 参数），精确计算受影响的缓存块范围并标记为脏块（`_block_dirty`），仅重新渲染脏块而非全部。行数变化时后续块也标记为脏，确保缓存索引一致。`_render_with_block_cache()` 改为跳过非脏缓存块，渲染后从 `_block_dirty` 中移除。常规打字（修改 1-2 行）时仅重绘 1 个块，节省约 95% 渲染开销
- **拖放文件类型白名单**（SEC-009）：`MainWindow` 新增 `_SUPPORTED_DROP_EXTS` 类属性，仅允许 `.txt`、`.md`、`.py`、`.c`、`.cpp`、`.h`、`.java`、`.js`、`.json`、`.html`、`.css`、`.xml`、`.yaml`、`.yml`、`.toml`、`.ini`、`.log`、`.sql`、`.sh`、`.go`、`.rs` 等文本文件类型。`dropEvent` 中对非白名单扩展名弹出警告对话框，防止意外打开二进制文件
- **PDF/HTML导出安全**（SEC-008）：Markdown转PDF和转HTML时均显式禁用原始HTML渲染（`MarkdownIt("commonmark", {"html": False})`），python-markdown fallback 仅启用 tables 扩展，防止XSS注入攻击
- **插件API防护**（SEC-010）：`PluginAPI` 的 `MVP_READ_ONLY` 从类变量改为实例属性 `_mvp_read_only`，防止恶意插件通过类级别篡改权限检查标志
- **命令注册竞态修复**（SEC-011）：`PluginAPI.register_command()` 使用 `dict.setdefault()` 原子操作替代先检查后插入的两步操作，消除 TOCTOU（Time-of-Check-to-Time-of-Use）竞态条件
- **IME打字奖励误判修复**（BUG-020）：`Editor` 新增 `_is_pasting` 标志，重写 `insertFromMimeData()` 在粘贴时设置标志；`EditorTabWidget._on_text_changed()` 增加 `is_pasting` 检查，粘贴操作不再计入打字奖励；粘贴检测阈值 `_PASTE_THRESHOLD` 从 15 提升至 50，避免 IME 整句输入被误判为粘贴
- **分屏语义优化**（BUG-021/022）：`_split_editor()` 改为打开新空白文件而非当前文件，避免两个标签页编辑同一文件导致数据覆盖风险；菜单文本更新为"水平分屏（独立编辑）"/"垂直分屏（独立编辑）"，明确语义
- **封装违规修复**（BUG-023）：`MainWindow._check_daily_checkin()` 中 `self.config._savegame_manager` 改为 `self.config.savegame_manager`，使用公开属性而非私有属性
- **行尾符统一**（BUG-024）：`editor.py`、`menu_builder.py`、`plugin_manager.py` 三个文件的 CRLF 行尾符统一转换为 LF，配合 `.gitattributes` 的 `* text eol=lf` 规则
- **Markdown预览主题修复**：`MarkdownPreviewWidget._apply_theme_colors()` 增加 `isinstance(self.preview, PreviewBrowser)` 类型检查，修复主题初始化顺序导致的 `AttributeError`
- **工程化改进**（INFRA-007）：`.gitignore` 新增 `data/logs/`、`Thumbs.db`、`scripts/__pycache__/` 条目
- **Silent except 日志补全**（QUAL-029）：7 个文件中的 `except ... : pass` 全部添加 debug/warning 日志，包括 `minimap.py`（AttributeError）、`markdown_preview.py`（ValueError/IndexError）、`editor_tabs.py`（ValueError）、`config.py`（Exception）、`exceptions.py`（兜底 print）、`plugin_base.py`（ValueError）、`find_replace.py`（re.error）、`plugin_manager.py`（Exception）
- **主题切换响应完善**（QUAL-031）：`MainWindow._apply_theme()` 新增 `_game_placeholder` 样式更新；`FindReplaceBar._apply_theme_colors()` 末尾调用 `_update_match_label()` 确保匹配计数标签颜色随主题同步
- **ErrorHandler 正则收紧**（QUAL-033）：`_SENSITIVE_PATTERNS` 中 `File "..."` 和 `line N` 两条独立正则合并为 `File "...", line N`，避免误过滤"on line 10""第 5 行"等普通文案

**兼容性说明**

- 所有改动向后兼容，无需迁移现有配置或存档
- `_SUPPORTED_DROP_EXTS` 白名单可通过修改 `MainWindow` 类属性扩展，不影响已有功能
- `_is_pasting` 标志对非粘贴输入（键盘/IME）无影响，打字奖励逻辑仅在粘贴时跳过计数
- 分屏行为变更：旧版本分屏打开当前文件的副本，新版本分屏打开空白文件。此为破坏性变更，但旧行为存在数据覆盖风险，新行为更安全
- 文件保存异步化：保存操作不再阻塞 UI，但保存失败时标签页会恢复修改标记。调用方（`_save_current`/`_save_all`）的返回值语义不变，但磁盘写入实际在后台完成
- Markdown 增量更新仅对 QWebEngineView 有效，QTextBrowser（PreviewBrowser）模式仍走全量 setHtml 路径

## v1.6.5

**架构整改与安全修复**

- **Config 职责拆分**：将 `config.py` 中的存档管理和安全管理逻辑拆分为独立类。新建 `core/savegame_manager.py`（`SavegameManager`），负责存档加载/保存/加密状态/资源CRUD；新建 `core/security_manager.py`（`SecurityManager`），负责路径验证/文件操作安全/输入验证的集成管理。`Config` 类通过组合方式委托调用，保持对外接口兼容
- **数据存储抽象层移除**：删除 `src/storage/` 目录（`storage_interface.py`/`json_storage.py`/`sqlite_storage.py`/`storage_factory.py`/`storage_migrator.py`），因全项目无业务调用方。`test_storage.py` 已一并移除
- **LazyLoader 移除**：`LazyLoader` 类（register/get/add_deferred_init/run_deferred_inits）全项目无调用方，已移除。仅保留 `StartupProfiler` 启动性能分析器，阶段管理集中到 `main.py`
- **PluginManagerDialog 提取**：从 `plugin_manager.py` 中提取 `PluginManagerDialog` 为独立模块 `plugin_manager_dialog.py`，降低单文件复杂度
- **主题系统全局生效**：新建 `themes/theme_aware_mixin.py`（`ThemeAwareMixin`），所有 UI 组件通过继承此 Mixin 订阅 `theme_changed` 信号，主题切换时自动更新样式。编辑器和 Markdown 预览中的硬编码颜色已改为主题系统变量
- **加密存档保存逻辑修复**（SEC-003）：`SavegameManager.save()` 新增 `SavegameSaveResult` 枚举返回值（`SUCCESS`/`SKIPPED_ENCRYPTED_UNREAD`/`ENCRYPTION_FAILED`），加密但未解锁的存档返回 `SKIPPED_ENCRYPTED_UNREAD` 而非静默跳过。MainWindow 在关闭时检查此状态并弹出密码输入对话框，供用户解锁存档后保存
- **加密存档解锁数据恢复**：修复 `set_encryption_password()` 在从加密未读状态解锁时，未重新加载原始加密数据导致内存数据为默认值的安全隐患。解锁时现在自动调用 `decrypt_savegame()` 加载原始数据，密码错误则恢复加密未读状态
- **加密存档加载安全备份**：`load()` 在进入加密未读状态（无密码或解密失败）时，自动备份加密文件（`.encrypted.bak`），作为数据恢复安全网
- **SavegameManager 重复初始化修复**：`Config.__init__()` 中创建 `SavegameManager` 实例后，`_load_all()` 不再重复创建新实例，仅调用 `load()` 加载数据，避免状态不一致
- **版本号统一引用**：所有版本号引用统一使用 `from src import __version__`，消除硬编码字符串
- **集中式版本管理**：`src/__init__.py` 新增 `get_version()` 和 `get_version_tuple()` 工具函数，作为版本号唯一真相源。`pyproject.toml` 改用 `dynamic = ["version"]` + `setuptools.dynamic` 从 `src.__version__` 动态读取版本。`plugin_base.py` 的 `min_app_version` 默认值改为引用 `_app_version`，插件示例文件同步更新。新建 `scripts/verify_version.py` 版本一致性验证工具，`main.py` 启动时自动检查版本一致性
- **每日签到**：`SavegameManager` 新增 `check_daily_checkin()` 方法，每日首次启动自动发放签到奖励（燃料/弹药/钢材/铝材各+100），通过小秘书提示

## v1.6.4

**阶段五：可扩展性架构及重构实施**

- **插件接口规范**：新建 `plugins/plugin_base.py`，定义完整插件生命周期（load/activate/deactivate/unload）、元数据规范（PluginMeta）、权限枚举（PluginPermission），最低兼容版本默认 1.6.4
- **插件沙箱隔离**：新建 `plugins/plugin_sandbox.py`，实现插件运行隔离（独立线程执行）、超时控制（默认30秒）、权限检查（MVP阶段严格只读访问），未授权访问抛出 `SandboxViolationError`，超时抛出 `SandboxTimeoutError`
- **插件管理系统**：新建 `plugins/plugin_manager.py`，实现从 `plugins/` 目录递归扫描插件包、验证清单完整性（plugin.json 必需字段）、插件注册/激活/停用/卸载管理接口、热加载机制（reload_plugin 不重启更新插件）
- **示例插件**：新建 `plugins/hello_panzer/`（基础功能插件，展示生命周期和只读API）和 `plugins/word_counter/`（UI扩展插件，展示编辑器交互和状态栏集成）
- **插件API文档**：新建 `plugins/plugin_api.md`，包含完整的插件开发指南、权限系统说明、沙箱隔离规范、PluginAPI接口参考和示例代码
- **主题系统**：新建 `themes/theme_engine.py`，支持JSON/YAML格式外部主题加载、颜色方案解析、QSS样式表自动生成、主题切换覆盖所有UI元素。新建 `themes/theme_preview.py`，提供主题预览对话框和实时预览功能
- **数据存储抽象层**：新建 `storage/storage_interface.py`，定义IStorage接口（CRUD/事务/元数据操作标准方法）。新建 `storage/json_storage.py`（JSON文件存储适配器）和 `storage/sqlite_storage.py`（SQLite数据库存储适配器）。新建 `storage/storage_factory.py`（存储实现工厂）和 `storage/storage_migrator.py`（存储间数据迁移工具）
- **主窗口集成**：修改 `main_window.py`，在启动流程中初始化主题引擎和插件管理器，菜单栏新增主题管理和插件管理入口
- **单元测试**：新增 `test_plugin_system.py`、`test_plugin_manager.py`、`test_theme_system.py`，覆盖插件生命周期、沙箱隔离、主题加载解析

## v1.6.3

**阶段四：系统安全性强化与防护机制建设**

- **路径安全验证模块**：新建 `security/path_validator.py`，实现路径规范化（`os.path.realpath`）、安全路径白名单机制、目录穿越攻击防护（`../`/`..\\` 检测）。支持 Windows 大小写不敏感文件系统和 `\\?\` 长路径前缀处理，路径长度限制 260 字符，控制字符检测
- **文件操作安全控制**：新建 `security/file_guard.py`，实现文件大小限制机制（默认 50MB，可配置）和操作超时控制（默认 30 秒）。使用线程实现超时中断与资源释放，正确处理符号链接和稀疏文件的大小计算，禁止使用 `os.path.getsize` 简单检测
- **存档数据加密系统**：新建 `security/crypto_manager.py`，基于用户密码使用 PBKDF2（600,000 次迭代）派生密钥，采用 AES-GCM 加密模式保护 `savegame.json`。支持未加密存档向加密格式的无缝迁移，迁移前自动备份，迁移后验证数据一致性。提供密码验证和加密状态检测接口
- **输入验证统一框架**：新建 `security/input_validator.py`，实现文件名验证（过滤非法字符、Windows 保留名称、路径注入、长度限制 255）、搜索内容验证（XSS/注入模式检测、长度限制 10,000）、设置值验证（类型检查、范围限制、允许值列表）。提供 `sanitize_filename` 清洗接口
- **安全模块集成**：修改 `config.py`、`editor_tabs.py`、`file_tree.py`、`find_replace.py`，所有文件操作通过 `FileGuard` 安全读写，新建/重命名文件通过 `InputValidator` 验证，搜索内容通过注入检测，存档支持加密/解密
- **单元测试**：新增 `test_path_validator.py`、`test_file_guard.py`、`test_crypto_manager.py`、`test_input_validator.py`，安全模块测试覆盖率达 93%

**Bug 修复**

- **修复窗口无法缩放**：修正 `dpi_helper.py` 中 `init_dpi()` 的双重缩放问题。当 `Qt.AA_EnableHighDpiScaling` 已启用时，Qt 自动处理 DPI 缩放，`scale()` 不应再乘以 `devicePixelRatio`，否则 `setMinimumSize(scale(800), scale(600))` 在 200% 缩放下变为 1600×1200，超出屏幕分辨率导致窗口无法调整大小
- **修复小秘书组件尺寸过大**：重构 `secretary_widget.py` 尺寸机制，从固定像素值（210×380）改为基于窗口面积的百分比控制。默认占窗口面积 7%，范围 3%~20%，可在「记事本设置 → 小秘书」中通过滑块调节，设置实时生效并持久化保存。小秘书随窗口缩放自动重新计算尺寸，保持 210:380 宽高比

**阶段三：用户体验提升优化与实现**

- **高 DPI 适配**：新建 `utils/dpi_helper.py`，实现基于 `devicePixelRatio` 的动态缩放机制。应用启动时自动启用 `Qt.AA_EnableHighDpiScaling`，所有视觉元素尺寸使用相对单位（`scale()`/`scale_size()`/`scale_font()`/`scale_stylesheet()`），支持 100%~200% 缩放比例下正常显示
- **小秘书位置跟随重构**：重构 `secretary_widget.py` 位置跟踪逻辑，使用 `eventFilter` 实时监听父容器 `resize`/`move` 事件，采用防抖机制（≤50ms）避免频繁更新，动态位置计算算法确保立绘始终右下对齐且不越界，支持窗口最大化/最小化/任意尺寸调整/多显示器拖动
- **快捷键系统**：新建 `core/shortcut_manager.py`，实现快捷键注册、冲突检测（系统级 + 应用内部）、自定义修改与持久化。`MenuBuilder` 已接入 `ShortcutManager`，所有菜单项通过 `manager.register()` 注册，用户在快捷键面板自定义的快捷键能真正生效。新建 `ui/shortcut_panel.py` 快捷键提示面板（`Ctrl+/` 调出），支持搜索、按功能模块分类展示、双击编辑快捷键。`settings.json` 新增 `shortcuts` 配置段
- **错误提示系统优化**：新建 `utils/error_handler.py`，实现统一错误处理中间层。8 类错误分类（文件/网络/配置/游戏/编辑器/权限/内存/通用），每类含默认建议操作。敏感信息过滤（路径/堆栈/IP/密码/Token），确保不泄露内部信息。自定义错误处理器注册机制，支持回退到默认对话框
- **单元测试**：新增 `test_dpi_helper.py`、`test_error_handler.py`、`test_shortcut_manager.py`，阶段三新增模块测试覆盖率达 93%

## v1.6.2

**阶段一：基础设施与代码质量重构**

- **结构化日志系统**：新建 `utils/logger.py`，统一日志级别（DEBUG/INFO/WARNING/ERROR）、格式（时间戳+模块+级别+消息）、输出位置（控制台 + 滚动文件，单文件最大5MB，保留3个备份）。日志目录自动创建，集成到 `main.py` 启动流程
- **统一异常处理装饰器 `@safe_call`**：新建 `utils/exceptions.py`，实现 `@safe_call` 装饰器自动捕获异常并记录日志。替换项目中所有 `except Exception: pass` 和 `except: pass` 模式，确保异常不再被静默吞掉。修复了重构过程中发现的 `QMessageBox` 参数错误
- **main_window.py 模块拆分**（1099行 → 677行）：
  - `game/game_engine.py`：挂机收益计算引擎（在线/离线奖励、资源上限检查）
  - `core/timer_manager.py`：定时器管理中心（自动保存、统计更新、挂机奖励定时器统一管理）
  - `core/event_bus.py`：事件路由系统（信号连接集中管理，解耦各模块间通信）
  - `core/menu_builder.py`：菜单构建器（菜单栏构建逻辑提取，支持动态菜单项）
- **editor.py 模块拆分**（1152行 → 546行）：
  - `editor/editor_actions.py`：行操作（删除/上移/下移/复制行）、大小写转换、JSON/XML格式化
  - `editor/auto_pair_handler.py`：括号/引号自动配对逻辑（Mixin模式，支持中英文标点）
- **类型提示与 mypy 集成**：为所有重构模块添加完整类型提示，在 `pyproject.toml` 中配置 mypy，配置 Mixin 模式的类型检查豁免规则
- **pytest 测试框架搭建**：安装 pytest/pytest-cov/pytest-qt，创建 `pyproject.toml` 配置，编写 187 个单元测试覆盖所有重构模块，核心模块覆盖率达 30.7%

**阶段二：性能优化攻坚**

- **editor.py 虚拟滚动**：新建 `editor/virtual_scroll.py`，实现 `VirtualScrollManager`。仅渲染当前可视区域内容，上下各保留 BUFFER_LINES 行缓冲区。大文件（≥50000行）自动启用延迟语法高亮，仅高亮可视区域及缓冲区内的代码块。滚动时通过 `QTimer.singleShot` 延迟触发高亮更新，避免滚动过程中阻塞渲染
- **minimap.py 渲染优化**：重构 `_render_content()` 方法，实现块级缓存（BLOCK_SIZE=50行/块）+ 批量渲染。使用 `QPicture` 缓存每个块的渲染结果，仅在内容变更时标记对应缓存块为脏块并重新渲染。将逐字符渲染改为按颜色分段批量绘制，显著减少 `QPainter` 状态切换次数
- **highlight_code_html() 异步渲染**：新建 `editor/async_highlight.py`，实现 `HighlightWorker`（QThread）和 `AsyncHighlightRenderer`。渲染工作在后台线程执行，主线程通过 `Qt.ConnectionType.QueuedConnection` 信号接收结果。支持最多 2 个并发渲染线程、任务优先级队列、10秒超时自动取消、渲染结果 LRU 缓存（50条）。集成到 `markdown_preview.py`，先渲染占位符再异步替换高亮结果
- **markdown_preview.py 增量渲染优化**：新建 `editor/incremental_renderer.py`，实现 `IncrementalRenderer` 和 `LRUCache`。基于 MD5 哈希的渲染结果缓存（容量50），相同文本直接返回缓存。行级变更检测，仅当文本实际变更时才重新调用渲染函数。代码块懒加载：异步模式下先显示纯文本占位，高亮完成后替换
- **应用启动性能优化**：新建 `utils/lazy_loader.py`，实现 `StartupProfiler` 启动性能分析器。`main.py` 中延迟导入 MainWindow，各初始化阶段加入性能分析标记。`_restore_state()` 改为延迟打开文件：先打开第一个文件使窗口快速呈现，剩余文件通过 `QTimer.singleShot(0)` 在事件循环空闲时逐个加载（原 `LazyLoader` 类已移除，因无业务调用方）
- **性能基准测试体系**：创建 `benchmarks/` 目录，包含 `test_data_generator.py`（生成小型500行/中型5000行/大型50000行测试文件）和 `run_baseline.py`（自动化基准测试运行器）。测量指标包括：文件打开时间、滚动FPS、缩略图渲染时间、代码高亮时间、内存占用、启动时间
- **Feature Flag 系统**：新建 `utils/feature_flags.py`，实现 5 个性能优化开关（`virtual_scroll`/`minimap_block_cache`/`async_highlight`/`markdown_incremental`/`lazy_loading`），默认全部关闭使用旧有实现路径。配置持久化到 `feature_flags.json`，支持运行时动态切换

## v1.6.1

- **修复：括号/引号自动配对崩溃bug**：修复在两字符中间输入括号后删除再输入中文引号时程序崩溃的严重问题（退出码 0xC0000409），将内联函数 `_pick_single_cjk_quote` 提取为类方法以解决作用域冲突
- **修复：自动配对触发条件过于宽松**：将"任意一侧有括号/引号就自动配对"改为"仅当光标左右恰好是互相匹配的一对符号时才自动配对"，避免在 `）你` 等单侧括号/引号旁误触发配对
- **新增：智能光标定位**：在单独左括号/引号（如 `(`）后输入对应右括号/引号（如 `)`）时，自动将光标移到符号中间，方便连续输入

## v1.6

- **新增：括号/引号自动配对：支持英文 () [] {} "" '' 与中文 （）【】「」『』《》〈〉""''；中文输入法（IME）输入中文标点同样生效；支持"已有配对符号之间继续输入并自动补全"的嵌套输入；右括号/右引号可跳过已有同字符；Backspace 支持成对删除；选中文本时输入括号/引号会自动包裹选区；可在记事本设置中开关**
- **新增：行操作快捷键**：
  - `Ctrl+Shift+K`：删除当前行
  - `Alt+↑`：上移当前行
  - `Alt+↓`：下移当前行
  - `Ctrl+Shift+D`：复制当前行到下一行
  - 以上操作在菜单栏「编辑 → 行操作」子菜单中也可访问
- **新增：大小写转换**：
  - `Ctrl+Shift+U`：循环切换选中文本的大小写（全大写 → 全小写 → 全大写）
  - 右键菜单新增「大小写转换」子菜单，支持：转为大写、转为小写、首字母大写、切换大小写
  - 菜单栏「编辑 → 大小写转换」子菜单中也可访问
- **新增：转到行功能**：`Ctrl+G` 弹出对话框，输入行号后快速跳转到指定行；菜单栏「编辑 → 转到行...」也可访问
- **新增：JSON/XML格式化**：当打开 JSON 或 XML/HTML 文件时，右键菜单显示「格式化文档」选项，一键美化缩进；JSON格式化后缩进为4空格，XML格式化后缩进为2空格

## v1.5.5

- **修复：显示行号开关生效**：记事本设置中的「显示行号」开关现在可以正确控制行号显示/隐藏，修改后即时生效
- **修复：高亮当前行开关生效**：记事本设置中的「高亮当前行」开关现在可以正确控制当前行高亮，修改后即时生效
- **修复：字体大小设置生效**：记事本设置中修改字体大小后立即应用到所有已打开的编辑器（此前仅「视图→缩放」有效）
- **新增：自定义字体选择**：记事本设置中新增字体选择下拉框（QFontComboBox），可从本地字体库中选择任意字体，确认后即时应用
- **文案修改**：「自动缩略图（仅代码文件）」更名为「自动开关缩略图」，含义更清晰

## v1.5.4

- **增强型查找替换**：支持正则表达式、大小写敏感、全词匹配，实时显示「第 N/M 个匹配」计数
- **标签页拖拽移动文件**：将标签拖到文件树的文件夹上即可移动文件
- **Markdown 本地图片支持**：预览中自动解析相对路径图片（如 `![](./img.png)`）
- **记事本设置对话框**：统一管理显示、缩略图、编辑器等选项，「自动缩略图（仅代码文件）」选项移入其中
- **修复缩略图切换卡死 Bug**：`Ctrl+M` 切换缩略图时程序卡死的严重问题已修复

## v1.5.3

- 文件树最小宽度调整至约100px并保留拖拽完全折叠功能
- 修复编辑器首次显示时行号区与文本重叠导致左侧文字被遮挡的问题
- 文件树与编辑区的分割比例现在会自动保存和恢复

## v1.5.2

- 预览代码高亮：Markdown预览中的代码块自动语法着色（Pygments内联样式），配色与左侧编辑器完全一致
- 代码块样式升级：浅蓝色背景（`#EDF3FA`）+ 蓝色左边框（`#4A86C8`），仿PyCharm风格
- 代码块一键复制：代码块左上角📋按钮，点击即复制原始代码到系统剪贴板
- 高亮主题系统：新增 `highlight_themes.py`，统一管理编辑器和预览的配色方案，可通过 `settings.json` 切换主题
- 修复代码块尾部空行：去除 `fenced_code` 扩展在代码块末尾附加的多余换行

## v1.5.1

- 代码缩略图（Minimap）：编辑器右侧鸟瞰图，彩色像素块呈现语法高亮，点击/拖拽快速导航
- 语法高亮配色更新：从VS Code风格切换为PyCharm IntelliJ Light风格（字符串绿色、注释灰色斜体、关键字深蓝加粗）
- Markdown预览改进：预览面板改为PyCharm风格（深色标题、浅灰代码块），去除`nl2br`/`codehilite`扩展以修正排版问题
- Markdown编辑器高亮增强：支持跨行代码块状态追踪（代码块内等宽字体+浅灰背景），标题分级显示

## v1.5

- 语法高亮：基于Pygments，支持30+编程语言
- Markdown分屏预览：左侧编辑，右侧实时渲染
- 自动缩进：智能缩进，Tab插入4空格
- 行宽模式切换：不换行 / 限制行宽
- 修复zip打包中文文件名乱码

## v1.4.1

- 资源平衡调整（前三项均衡，铝材3:1）
- 立绘架构重构（角色/皮肤/状态）
- 修复立绘路径从程序目录读取

## v1.4

- 小秘书定位修复、气泡增大
- 文件夹展开符号修复
- 配置路径持久化
- 编码保持与另存为编码选择

## v1.2

- 挂机机制（在线/离线资源获取）
- 编码检测（UTF-8→GBK→UTF-16）

## v1.0

- 基础记事本功能、游戏框架、小秘书系统
