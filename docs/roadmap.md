# 路线图

本文件记录 PanzerNote 尚未完成的功能规划与后续方向。已完成功能请参考 [CHANGELOG.md](../CHANGELOG.md)，架构设计请参考 [architecture.md](architecture.md)。

## 未完成规划

### 建造系统

投入资源建造角色，按一定配方和概率产出不同稀有度的战车娘。建造结果写入图鉴并解锁对应立绘。

- 资源投入面板（燃料/弹药/钢材/铝材配比）
- 建造配方与产出概率表
- 建造队列与时间机制
- 建造结果展示与立绘解锁

### 图鉴收集

收集所有战车娘角色，按编号/类型/阵营分类展示，记录解锁状态、大破立绘和皮肤。

- 图鉴主界面（网格/列表视图切换）
- 角色详情页（立绘/属性/台词）
- 已收集/未收集统计
- 皮肤解锁条件

### 车库

管理已获得的战车娘，编队、强化、退役等操作。

- 角色列表与筛选
- 编队系统
- 强化与升级
- 退役与资源回收

### 游戏设置界面

完善游戏相关设置对话框，统一管理游戏内选项。

- 资源参数配置
- 难度调节
- 音效与提示开关
- 游戏存档导入/导出

## 主题系统迁移（已完成）

Wave 8（B1~B8）完成主题系统重构为 Theme v2：删除 v1 主题引擎与外部主题（JSON/YAML）加载，UI 组件全部迁移到 v2 token / recipe，语法高亮与 Markdown 预览配色统一从 v2 调色板读取。剩余硬编码颜色与状态见 [color_audit.md](theme-design/color_audit.md)。

- ✅ 编辑器硬编码颜色 → 主题 token
- ✅ Markdown 预览代码块配色 → 主题 token
- ✅ 弹窗与浮窗深色样式补全
- ✅ 主题作者指南：Theme v2 主题包格式与校验规则见 [theme_authoring.md](theme-design/theme_authoring.md)（B9 B6）
- ~~外部主题作者指南（`docs/theme_system.md`）~~：外部主题机制已随 v1 删除；v2 主题制作文档已由 theme_authoring.md 承接

## 渲染轻量化（已完成）

方案 A（分支 `refactor20260910-lightweight_preview`）以 `QTextBrowser` + `QTextDocument` 承载 Markdown 预览，以 `QPdfWriter` + `QTextDocument.print()` 承载 PDF 导出，摘除 `PyQt6-WebEngine` 依赖；打包体积 538 MB → **90.1 MB**（规格见 `PanzerNote.spec`）。对照方案 B（保留 WebEngine、仅做打包瘦身，362.5 MB）见分支 `refactor20260910-webengine_single_path`。

- ✅ 预览渲染唯一化到 `QTextBrowser`（删除 WebEngine 分支与启动锚点）
- ✅ PDF 导出改为 `QPdfWriter`（同步渲染，无 WebEngine 回调）
- ✅ 导出与预览共用语法高亮与亮色变体（深色主题导出为黑字浅底）
- ⚠️ 行号同步由 WebEngine JS 精确滚动降级为比例滚动（已接受）
- ~~WebEngine 预览 JS 局部增量更新~~：随 WebEngine 一并移除，预览改为全量 `setHtml`

## 文档完善

- `docs/user_guide.md`：面向终端用户的使用指南
- `docs/developer_guide.md`：开发、测试、提交规范
- `docs/branch_recovery.md`：分支事故与稳定基线记录（短期）
- ✅ `docs/theme_system.md`：v1 外部主题格式文档已随 v1 机制删除；Theme v2 主题包文档由 `docs/theme-design/theme_authoring.md` 承接
