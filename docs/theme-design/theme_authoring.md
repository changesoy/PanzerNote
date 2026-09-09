# PanzerNote Theme v2 主题作者指南（B9 B6-1）

> 状态：2026-09-09 定稿（对应 Wave 8 B1 Foundation 设计文档与 `src/themes/theme_v2/` 实现）。
> 本文档描述 Theme v2 主题包格式与校验规则，供开发第二/第三方视觉语言参考。
> v1 主题机制（外部 JSON/YAML）已随 Wave 8 删除，**v2 是唯一主题运行时**。

## 1. 主题包目录结构

每个主题一个自包含目录 `themes/<theme_id>/`：

```
themes/<theme_id>/
├── theme.json        # 必需：manifest（schema_version / 元信息 / shell_schema / renderer_profile）
├── variants/         # 必需：每变体一个 JSON，filename stem 即 VariantId
│   ├── dark.json
│   └── light.json
├── design.json       # 可选：spacing / radius / density / typography（缺省空 → 校验器给默认值）
├── recipes.json      # 可选：Component Recipe（style 通用属性 + renderer + renderer_params）
├── motion.json       # 可选：动效参数（缺省中性默认值）
└── icons.json        # 可选：图标 override（缺省空）
```

- **`variants/*.json` 的 filename stem 即 VariantId**（单一事实源）：文件内部**不写**
  `"id"` 字段。VariantId 必须匹配 `^[a-z0-9][a-z0-9-]*$`。
- **Default 主题 MUST 提供 `light` + `dark` 两个变体**；其他主题 `variants.size >= 1`
  合法（单变体主题直接只有 `variants/dark.json`）。
- 主题 id = 目录名。切换入口 `ThemeManager.request(theme_id, variant_id)`。

## 2. theme.json（manifest）

```json
{
  "schema_version": 2,
  "name": "PanzerNote Default",
  "family": "classic",
  "shell_schema": "workbench-v1",
  "renderer_profile": "classic-v1",
  "window_chrome": { "mode": "native" }
}
```

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| `schema_version` | 是 | 必须等于 `2`；`> supported` 被明确拒绝（可读错误），**不 silent fallback** |
| `name` | 是 | 非空字符串 |
| `family` | 是 | 字符串；**纯描述性元数据**（仅服务 Theme Manager 分组/展示），不影响 runtime 语义 |
| `shell_schema` | 是 | 必须 ∈ `{"workbench-v1"}`；未知 schema **拒绝加载，不触发 L2**（宿主 ABI 契约） |
| `renderer_profile` | 是 | 非空字符串（缺省 Renderer 集合 preset 名；组件级 recipe 可 override） |
| `window_chrome` | 否 | `mode` ∈ `{"native", "extended-native", "custom"}`；v2 第一版仅 `native` 稳定实现 |

## 3. variants/<id>.json（变体契约）

每个变体文件包含三块：`color_identity` / `tokens` / `syntax`。

```json
{
  "color_identity": {
    "strategy": "chromatic",
    "primary": "#0078D4",
    "accents": ["#0078D4"],
    "hue_family": "blue"
  },
  "tokens": { "...": "#RRGGBB" },
  "syntax": { "palette": "dark-default-v1", "overrides": {} }
}
```

### 3.1 color_identity（D27：归属 variant）

| 字段 | 规则 |
| --- | --- |
| `strategy` | ∈ `{"chromatic", "neutral", "multi"}`。`neutral`：`primary` 必须为 null、`accents` 必须为空 |
| `primary` | 合法颜色 `#RRGGBB[AA]`（chromatic/multi 必填） |
| `accents` | 颜色数组 |
| `hue_family` | 非空字符串（如 `blue` / `purple` / `neutral`） |

**用途**：分类 / 推荐 / 主题预览 / 资产匹配——**不直接参与渲染**。
渲染只依赖 semantic token。`mode`（明暗）由 variant id 表达，不重复声明。

### 3.2 tokens（semantic token 白名单）

- 全部键必须在 `TOKEN_WHITELIST` 内（见附录 A），值为合法颜色 `#RRGGBB[AA]`。
- 值引用：recipe 的 `style` 可直接引用 token 名（如 `"background": "surface_primary"`）。

### 3.3 syntax（D18：共享 palette + 薄 override）

```json
"syntax": { "palette": "light-default-v1", "overrides": { "syntax_keyword": "#..." } }
```

- `palette` 引用 `themes/syntax/palettes/<id>.json`（全局共享资源，不随主题复制）。
- `overrides` 键必须在 `SYNTAX_TOKEN_WHITELIST` 内（见附录 B），值为合法颜色。
- 浅继承：最终色 = palette 全量 + 本变体 overrides。
- **不依赖 UI accent 派生**：keyword/string/comment 显式写 palette。
- 引用的 palette 不存在 → activate 前报错（`ThemeResourceError`）。

## 4. design.json（变体共享的设计变量）

```json
{
  "spacing": { "space_1": 2, "space_2": 4, "space_3": 8 },
  "radius": { "radius_sm": 3, "radius_md": 6, "radius_lg": 10, "radius_full": 100 },
  "density": { "density_compact": 24, "density_default": 30, "density_comfortable": 36 },
  "typography": { "font_ui": "Inter, Microsoft YaHei", "font_mono": "JetBrains Mono, Consolas", "font_scale": 1.0 }
}
```

- 数值必须是非负整数（像素）。
- 键名自由（schematic），由消费端按需取用；禁止在页面里硬编码 magic spacing/radius。
- **亮/暗共享设计变量，仅 token 颜色分变体。**

## 5. recipes.json（Component Recipe）

Recipe 分两层：**通用 `style` 属性**（跨 renderer 通用）+ **`renderer_params` 专属参数**。
每个 recipe 声明 `renderer` id；校验器据此做 renderer resolution。

```json
{
  "button": {
    "renderer": "default-v1",
    "style": {
      "background": "accent",
      "hover_background": "focus",
      "pressed_background": "border_strong",
      "focus_border": "focus",
      "text": "#FFFFFF",
      "radius": "radius_md",
      "padding": "space_3"
    },
    "renderer_params": { }
  }
}
```

- **recipe key 必须单段 snake_case**（`^[a-z][a-z0-9_]*$`，如 `button` / `tree_item`，**不用点分**）。
- `style` 值支持两种形式：semantic token 名（解析为 variant 色值）或直接色值 `#RRGGBB[AA]`。
- `renderer` 必须已注册（内置兜底 `default-v1`）；未知 renderer id → `ThemeRendererError`。
- `renderer_params` 由对应 RendererContract 的 `accepted_params_schema` 校验（`default-v1` 为空 schema）。
- 现有 recipe key 清单见附录 C。**具体 Renderer（brutal-v1 / soft-motion-v1 等）属 B8，当前未实现**。

## 6. motion.json（动效参数）

```json
{ "duration_fast": 100, "duration_normal": 200, "easing": "ease-out" }
```

- 缺省中性默认值 `{"duration_fast": 100, "duration_normal": 200, "easing": "ease-out"}`。
- `duration_*` 非负整数；`easing` 非空字符串。
- 切换 fade 时长按等级分档（L0=150ms / L1=250ms）为第一版 ThemeTransitionController
  常量，不写入 motion.json（B8/B9 需要时再升格）。
- **用户偏好 > 主题偏好**：Reduced Motion 设置（Normal/Reduced/Off）优先于主题值。

## 7. icons.json（图标 override，D5/D24）

```json
{ "set": "lucide", "overrides": { "app.logo": "themes/<theme_id>/assets/logo.svg" } }
```

- `set`：非空字符串（当前仅内置 Lucide Registry 概念）。
- `overrides`：语义 key → 资源引用（**productivity 语义 key，不用 `game.*`**——游戏侧独立）。
- 资源引用受 **Theme Resource Contract** 约束（见 §8）。

## 8. Theme Resource Contract（activate 前校验）

引用资源（icons overrides 等）在 **activate 前**校验，绝不等 paint 时：

- 禁止 `http(s)://` 等 URL 引用（零运行时网络依赖）；
- 路径 normalize 后必须位于 theme root 或 approved shared root（`themes/syntax/`），
  不允许 `../` 越界；
- 扩展名白名单：`.svg / .png / .jpg / .jpeg / .webp / .gif`；
- 不存在的资源文件 → activate 前报错（`ThemeResourceError`）。

## 9. 校验流水线与错误类型

`ThemeValidator` 六阶段（顺序已定稿）：

```
parse → schema validation → semantic validation → renderer resolution
      → resource resolution → fallback validation → 构造 ThemeSnapshot
```

- **任何非法主题在 activate 前被拒绝**；`ThemeSnapshot` 只在流水线末尾构造（不可变）。
- 错误类型：`ThemeParseError`（JSON 解析）、`ThemeSchemaError`（结构/字段）、
  `ThemeSemanticError`（白名单/取值）、`ThemeRendererError`（未知 renderer）、
  `ThemeResourceError`（资源越界/缺失/类型）、`ThemeFallbackError`（缺少兜底 renderer）。
- **v2 加载失败 = 启动显式报错**（错误对话框 + 日志，`ThemeLoadError`），**永不静默回退 v1**。

运行时加载：`ThemeManager.prepare(theme_id, variant_id)`（无 QWidget 副作用）→
`commit()`（激活事务，失败回滚旧 snapshot）。生产路径当前恒 L0（同包变体切换）；
跨包换 Renderer 才进入 L1（须有注册的 RendererHost）。

## 10. 编写与验证流程

1. 新建目录 `themes/<theme_id>/`，按 §1 结构填 JSON（可从 `themes/default/` 复制改造）。
2. 校验：写单测或用现成流水线——

```python
from pathlib import Path
from src.themes.theme_v2.loader import ThemePackageLoader
from src.themes.theme_v2.validator import ThemeValidator
from src.themes.theme_v2.renderer_registry import RendererRegistry
from src.themes.theme_v2.resources import PaletteRegistry, ThemeResourceContract

root = Path("themes/<theme_id>")
palettes = PaletteRegistry()
for p in sorted(Path("themes/syntax/palettes").glob("*.json")):
    palettes.register(p.stem, __import__("json").loads(p.read_text(encoding="utf-8")))
validator = ThemeValidator(
    registry=RendererRegistry(),
    palette_registry=palettes,
    resource_contract=ThemeResourceContract(shared_root=Path("themes/syntax")),
)
snapshot = validator.validate(ThemePackageLoader().load(root))
print("OK", sorted(snapshot.variants))
```

3. 运行时切换冒烟：启动应用 → 主题管理器选择该主题 → 检查 L0 过渡与观感。
4. 双变体主题必须同时检查 dark/light 两套 token 与 syntax palette 引用。

## 11. 兼容性（切换等级判定）

- 兼容性比较 `shell_schema` + **Resolved Renderer Map**（组件级 renderer 相同 → L0；
  不同 → L1 局部替换计划；两合法 shell_schema 间切换才属 L2，当前不存在）。
- 写未知 `shell_schema` → 拒绝加载（**不触发 L2**）。
- 换 renderer 时不残留旧 renderer 私有字段；通用 recipe 不被某套主题污染。

## 附录 A：UI semantic token 白名单（TOKEN_WHITELIST）

```
surface_primary / surface_secondary / surface_raised
text_primary / text_secondary / text_muted
border_muted / border_strong
accent / focus / danger
accent_soft / on_accent
editor_background / editor_line_number / editor_current_line
editor_bracket_match_bg / editor_bracket_match_fg / editor_bracket_unmatched
editor_bookmark_bg / editor_bookmark_fg
editor_fold_marker / editor_fold_marker_collapsed
md_h1_fg / md_h2_fg / md_h3_fg / md_h456_fg
md_bold_fg / md_italic_fg
md_code_fg / md_code_bg
md_link_fg / md_image_fg / md_list_fg / md_quote_fg / md_hr_fg / md_fence_fg
md_code_block_fg / md_code_block_bg
md_preview_code_block_bg / md_preview_code_block_border
search_match_bg / search_current_bg / search_current_fg
minimap_viewport
```

## 附录 B：syntax token override 白名单（SYNTAX_TOKEN_WHITELIST）

```
syntax_keyword / syntax_keyword_type / syntax_builtin / syntax_class
syntax_function / syntax_variable / syntax_tag / syntax_namespace
syntax_string / syntax_string_escape / syntax_string_affix / syntax_string_doc
syntax_number / syntax_comment / syntax_operator / syntax_punctuation
syntax_text / syntax_error / syntax_deleted / syntax_inserted
syntax_heading / syntax_output
```

## 附录 C：现有 recipe key 清单（themes/default/recipes.json）

```
editor / tab / scrollbar / minimap / search / markdown
button / input / combo_box / menu / context_menu
checkbox / radio / slider / tooltip / tree_item
group_box / dialog / statusbar
```
