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

### Theme v2 多包化与剩余加固（Wave 8 B8，已延后）

Wave 8 按 B1~B9 推进：B1~B7 已实现并提交（v1 主题系统已删除），B9 部分完成
（补漏收尾 / 代码卫生 / 性能审计 / 硬编码复核 / packaging / license / 验收记录 /
主题作者文档）；**B8「第二视觉语言 / 跨包切换」未做，延后**——当前仓库只有 default 单个
主题包，产品路径注册 0 个 RendererHost，跨包 L1 流水线在生产中不会被触发。

- 第二主题包（真实第二视觉语言）与跨包切换 UI；具体 Renderer（`brutal-v1` / `soft-motion-v1` 等）见 [theme_authoring.md](theme-design/theme_authoring.md)
- 图标集：`icons.json` 的 `overrides` 机制已可用，但非 Lucide 的完整图标集尚未提供
- `ThemeValidator` 未强制 token 全覆盖 / recipe style 键集合（验收记录 F-3）：缺失时 QSS 生成期硬索引可能 KeyError，default 单包不触发
- `_retry_pending` 恢复路径不执行调用点收尾（config 持久化 / 全局 QSS 重涂 / DWM 标题栏，验收记录 F-4）
- 跨包 L1 路径的切换性能实测：现有 0.04 ms 基准只覆盖 L0 同包变体，见 [color_audit.md](theme-design/color_audit.md) 性能审计段
- 游戏侧视觉域与剩余 P2 加固项

> 主题配色治理现状与历史批次记录见 [color_audit.md](theme-design/color_audit.md)，
> Wave 8 逐格验收证据见 [wave8_acceptance.md](theme-design/wave8_acceptance.md)。

### 图片工作流的剩余边界

- 旧 `assets/` 目录的一次性迁移命令
- 浏览器侧（预览）健康诊断
- 相机 RAW 查看：解码需 LibRaw + numpy，包体约 54 MB，成本与收益不成比例

## 文档完善

- `docs/user_guide.md`：面向终端用户的使用指南
- `docs/developer_guide.md`：开发、测试、提交规范
- `docs/branch_recovery.md`：分支事故与稳定基线记录（短期）
- ✅ `docs/theme_system.md`：v1 外部主题格式文档已随 v1 机制删除；Theme v2 主题包文档由 `docs/theme-design/theme_authoring.md` 承接
