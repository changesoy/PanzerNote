# Color Audit

Baseline: fix20260703(3)-theme @ 78542d8875ba826cfdce256565aef55d003345a5

## Goal

This document records hardcoded colors and color-system inconsistencies.
This commit does not change runtime behavior.

## Reference Direction

PanzerNote dark theme should follow VS Code Dark Modern / Dark+ rather than JetBrains Darcula.

Reasons:

- Current editor background, selection color, Markdown preview code block, and `vscode_dark` highlighter already match VS Code more closely.
- JetBrains Darcula uses a warmer gray UI base such as #3C3F41, which would require a much broader palette migration.

## Allowed Hardcoded Colors

These are allowed for now:

| Area                                           | Reason                                                                                                         |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `src/themes/theme_engine.py`                   | Theme definitions are the source of truth                                                                      |
| `src/editor/highlight_themes.py`               | Syntax theme definitions are intentional palettes                                                              |
| `src/editor/syntax_highlighter.py`             | Markdown semantic highlighter palette; allowed but should stay aligned with VS Code                            |
| `src/editor/markdown_preview.py` HTML template | Self-contained rendered document CSS; allowed but should be gradually converted to explicit semantic variables |
| assets                                         | Real image/icon assets                                                                                         |
| tests                                          | Test fixtures                                                                                                  |

## Scan Patterns

Search patterns:

- `#[0-9a-fA-F]{3,8}`
- `rgb(`
- `rgba(`
- `QColor(`
- `setStyleSheet(`

Excluded paths:

- `src/themes/theme_engine.py`
- `src/editor/highlight_themes.py`
- `src/editor/syntax_highlighter.py`
- `assets/`
- `tests/`

## Summary

| File                                     | Count | Status                   | Notes                                                        |
| ---------------------------------------- | ----: | ------------------------ | ------------------------------------------------------------ |
| `src/editor/markdown_preview.py`         |    49 | Mostly allowed           | HTML template CSS and dark map; monitor carefully            |
| `src/editor/editor.py`                   |    21 | Needs migration          | gutter bookmark/fold colors and fallbacks                    |
| `src/editor/minimap.py`                  |    13 | Low priority             | most colors are fallback; theme path exists                  |
| `src/editor/find_replace.py`             |    10 | Needs migration          | search match/current match colors should become theme tokens |
| `src/ui/side_panel_host.py`              |     8 | Needs review             | checked button should not depend on Material purple          |
| `src/editor/secure_markdown_renderer.py` |     8 | Needs ownership decision | legacy/secure renderer may duplicate preview CSS             |
| `src/game/game_sidebar.py`               |     7 | Needs review             | likely resource/status colors                                |
| `src/themes/theme_preview.py`            |     4 | Low priority             | color swatches are intentionally literal                     |
| `src/game/secretary_widget.py`           |     4 | Needs review             | bubble/status colors should map to theme tokens              |
| `src/ui/command_palette.py`              |     3 | Low priority             | hint fallback only; themed after init                        |
| `src/editor/find_in_files_panel.py`      |     2 | Low priority             | already mostly themed                                        |

## Unreasonable Color Arrangements

### 1. Mixed Material and VS Code accent systems

~~Current dark theme mixes Material-like `#BB86FC` / `#03DAC6` with VS Code-like editor, selection and code colors.~~

**RESOLVED (Batch E)**: Dark theme `primary` switched to VS Code blue `#0078D4`, `primary_dark`/`hover_bg` to `#026EC1`, `focus_border` to `#0078D4`.

### 2. `primary_light` is semantically overloaded

~~`primary_light` currently behaves like selection background.~~
**RESOLVED**: `selection_bg`, `selection_fg`, `hover_bg`, `active_bg` tokens added and wired.

### 3. Dark surface layers are too flat

~~Many surfaces use `#1E1E1E`.~~
**RESOLVED (Batch E)**: Dark theme now uses separate levels:

- window / title / status: `#181818`
- editor: `#1F1F1F`
- widget (sidebar): `#202020`
- card: `#2B2B2B`

### 4. Search highlight colors live in `find_replace.py`

~~Move later to: `search_match_bg`, `search_current_bg`, `search_current_fg`~~
**RESOLVED (Batch C)**: `find_replace.py` and `find_in_files_panel.py` now read from search tokens.

### 5. Gutter bookmark and fold marker colors live in `editor.py`

~~Move later to: `editor_bookmark_bg`, `editor_bookmark_fg`, `editor_fold_marker`, `editor_fold_marker_collapsed`~~
**RESOLVED (Batch B)**: `editor.py` now reads from bookmark/fold tokens.

### 6. Side panel selected state depends on `primary`

~~If `primary` remains `#BB86FC`, white text is not ideal.~~
**RESOLVED (Batch E)**: `primary` is now VS Code blue `#0078D4`; white text on blue is the intended contrast.

## Target Token Values (VS Code Dark Modern / Dark+)

PanzerNote dark theme targets VS Code Dark Modern / Dark+, not JetBrains Darcula.

| Token                                  |    Target | Usage                        |
| -------------------------------------- | --------: | ---------------------------- |
| `bg_window` / `bg_title` / `bg_status` | `#181818` | Shell, title bar, status bar |
| `bg_editor`                            | `#1F1F1F` | Editor viewport              |
| `bg_widget`                            | `#202020` | Sidebars, panels             |
| `bg_card` / `bg_codeblock`             | `#2B2B2B` | Cards, code blocks           |
| `bg_input`                             | `#313131` | Input fields                 |
| `primary`                              | `#0078D4` | Primary accent               |
| `primary_dark` / `hover_bg`            | `#026EC1` | Hover, pressed states        |
| `selection_bg`                         | `#264F78` | Selection background         |
| `focus_border`                         | `#0078D4` | Focus ring                   |
| `search_match_bg`                      | `#3A3D41` | Find match highlight         |
| `search_current_bg`                    | `#515C6A` | Current find match           |
| `search_current_fg`                    | `#FFFFFF` | Current find match text      |
| `editor_bookmark_bg`                   | `#0078D4` | Bookmark gutter marker       |
| `editor_bookmark_fg`                   | `#FFFFFF` | Bookmark gutter marker text  |
| `editor_fold_marker`                   | `#808080` | Fold marker (expanded)       |
| `editor_fold_marker_collapsed`         | `#C5C5C5` | Fold marker (collapsed)      |

### Batch Strategy

- **Batch A**: Add tokens only, with old values as defaults. No visible UI change.
- **Batch B / C / D**: Gradually wire components to use tokens.
- **Batch E**: After all components use semantic tokens, switch the built-in dark theme palette to these target values.

## Migration Batches

### Batch A: ThemeColorScheme semantic tokens ✅ COMPLETED

Added tokens with old values as defaults (no UI change):

- `selection_bg` → light: `#BBDEFB`, dark: `#264F78`
- `selection_fg` → light: `#212121`, dark: `#E0E0E0`
- `hover_bg` → light: `#BBDEFB`, dark: `#264F78`
- `active_bg` → light: `#1976D2`, dark: `#985EFF`
- `focus_border` → light: `#2196F3`, dark: `#BB86FC`
- `search_match_bg` → light: `#FFEE58`, dark: `#6B6B00`
- `search_current_bg` → light: `#FF9800`, dark: `#B47800`
- `search_current_fg` → light/dark: `#FFFFFF`
- `editor_bookmark_bg` → light: `#FF9800`, dark: `#BB86FC`
- `editor_bookmark_fg` → light/dark: `#FFFFFF`
- `editor_fold_marker` → light: `#4CAF50`, dark: `#81C784`
- `editor_fold_marker_collapsed` → light: `#66BB6A`, dark: `#A5D6A7`

_Note: Dark theme values match existing hardcoded colors in editor.py/find_replace.py to ensure zero visual change._

### Batch B: Editor auxiliary colors ✅ COMPLETED

Migrated:

- `editor.py`: fold markers → `editor_fold_marker` / `editor_fold_marker_collapsed`; bookmarks → `editor_bookmark_bg` / `editor_bookmark_fg`
- `syntax_highlighter.py`: Markdown semantic highlighter now reads from `md_*` theme tokens (h1-h6, code, link, quote, etc.)
- `minimap.py`: fallback colors aligned with theme defaults (`minimap_bg`, `border`, `text_disabled`, `primary`)

_Note: `find_replace.py` search highlights moved to Batch C (search tokens)._

### Batch C: Sidebar and command surfaces ✅ COMPLETED

Migrated:

- `side_panel_host.py`: audited, already fully token-driven (no hardcoded colors)
- `command_palette.py`: hint label fallback aligned with `text_secondary` default
- `find_in_files_panel.py`: text fallbacks aligned with `text_secondary`
- `game_sidebar.py`: `GameIconButton` colors wired to `game_build`/`game_garage`/`game_collection` tokens

### Batch D: Legacy Markdown renderer decision ✅ COMPLETED

`secure_markdown_renderer.py` still has active call paths (export_service, markdown_preview fallback). Kept as-is.
`markdown_preview.py` CSS refactored: `PREVIEW_HTML_TEMPLATE` hardcoded colors replaced with CSS variables; `_DARK_COLOR_MAP` and `_get_dark_preview_template` removed; `_build_preview_css_vars` injects `:root` overrides from theme tokens.

### Batch E: Palette normalization ✅ COMPLETED

Switched built-in dark theme palette to VS Code Dark Modern / Dark+ target values:

- `background`/`surface`: `#1E1E1E` → `#181818`
- `editor_bg`: `#1E1E1E` → `#1F1F1F`
- `sidebar_bg`: `#1E1E1E` → `#202020`
- `card`: `#2D2D2D` → `#2B2B2B`
- `primary`: `#BB86FC` → `#0078D4`
- `primary_dark`/`hover_bg`/`active_bg`: `#985EFF`/`#264F78` → `#026EC1`
- `focus_border`: `#BB86FC` → `#0078D4`
- `search_match_bg`: `#6B6B00` → `#3A3D41`
- `search_current_bg`: `#B47800` → `#515C6A`
- `editor_bookmark_bg`: `#BB86FC` → `#0078D4`
- `editor_fold_marker`: `#81C784` → `#808080`
- `editor_fold_marker_collapsed`: `#A5D6A7` → `#C5C5C5`
- `statusbar_bg`/`menubar_bg`: `#1E1E1E` → `#181818`

Light theme palette unchanged.

## Verification Checklist

- Start app in dark theme.
- Restart while dark theme is persisted.
- Open `.md` file and verify preview is not blank.
- Open `.py` file and verify syntax highlight.
- Trigger completion popup.
- Open theme manager.
- Open command palette.
- Open find/replace bar.
- Open find-in-files panel.
- Toggle sidebar panels.
