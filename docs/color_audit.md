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

Current dark theme mixes Material-like `#BB86FC` / `#03DAC6` with VS Code-like editor, selection and code colors.

Recommendation:
Future palette migration should move to VS Code blue:

- `primary`: `#0078D4`
- `primary_dark`: `#026EC1`
- `selection_bg`: `#264F78`
- `focus_border`: `#0078D4`

Do not change this in the audit commit.

### 2. `primary_light` is semantically overloaded

`primary_light` currently behaves like selection background.
Future migration should introduce:

- `selection_bg`
- `selection_fg`
- `hover_bg`
- `active_bg`

### 3. Dark surface layers are too flat

Many surfaces use `#1E1E1E`.
Future migration should introduce separate levels:

- window / title / status: `#181818`
- editor: `#1F1F1F` or `#1E1E1E`
- widget: `#202020`
- card / code block: `#2B2B2B`
- input: `#313131`

### 4. Search highlight colors live in `find_replace.py`

Move later to:

- `search_match_bg`
- `search_current_bg`
- `search_current_fg`

### 5. Gutter bookmark and fold marker colors live in `editor.py`

Move later to:

- `editor_bookmark_bg`
- `editor_bookmark_fg`
- `editor_fold_marker`
- `editor_fold_marker_collapsed`

### 6. Side panel selected state depends on `primary`

If `primary` remains `#BB86FC`, white text is not ideal.
After palette migration, use VS Code blue or `selection_bg`.

## Target Token Values (VS Code Dark Modern / Dark+)

PanzerNote dark theme targets VS Code Dark Modern / Dark+, not JetBrains Darcula.

| Token                                     |                                    Target | Usage                            |
| ----------------------------------------- | ----------------------------------------: | -------------------------------- |
| `bg_window` / `bg_title` / `bg_status`    |                                 `#181818` | Shell, title bar, status bar     |
| `bg_editor`                               |                                 `#1F1F1F` | Editor viewport                  |
| `bg_widget`                               |                                 `#202020` | Sidebars, panels                 |
| `bg_card` / `bg_codeblock`                |                                 `#2B2B2B` | Cards, code blocks               |
| `bg_input`                                |                                 `#313131` | Input fields                     |
| `primary`                                 |                                 `#0078D4` | Primary accent                   |
| `primary_dark` / `hover_bg`               |                                 `#026EC1` | Hover, pressed states            |
| `selection_bg`                            |                                 `#264F78` | Selection background             |
| `focus_border`                            |                                 `#0078D4` | Focus ring                       |
| `search_match_bg`                         |                                 `#3A3D41` | Find match highlight             |
| `search_current_bg`                       |                                 `#515C6A` | Current find match               |
| `search_current_fg`                       |                                 `#FFFFFF` | Current find match text          |
| `editor_bookmark_bg`                      |                                 `#0078D4` | Bookmark gutter marker           |
| `editor_bookmark_fg`                      |                                 `#FFFFFF` | Bookmark gutter marker text      |
| `editor_fold_marker`                      |                                 `#808080` | Fold marker (expanded)           |
| `editor_fold_marker_collapsed`            |                                 `#C5C5C5` | Fold marker (collapsed)          |

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

*Note: Dark theme values match existing hardcoded colors in editor.py/find_replace.py to ensure zero visual change.*

### Batch B: Editor auxiliary colors ✅ COMPLETED

Migrated:
- `editor.py`: fold markers → `editor_fold_marker` / `editor_fold_marker_collapsed`; bookmarks → `editor_bookmark_bg` / `editor_bookmark_fg`
- `syntax_highlighter.py`: Markdown semantic highlighter now reads from `md_*` theme tokens (h1-h6, code, link, quote, etc.)
- `minimap.py`: fallback colors aligned with theme defaults (`minimap_bg`, `border`, `text_disabled`, `primary`)

*Note: `find_replace.py` search highlights moved to Batch C (search tokens).*

### Batch C: Sidebar and command surfaces

Migrate `side_panel_host.py`, `command_palette.py`, `find_in_files_panel.py`.

### Batch D: Legacy Markdown renderer decision

Decide whether `secure_markdown_renderer.py` is still used.
If yes, align it with `markdown_preview.py`.
If no, deprecate or isolate it.

### Batch E: Palette normalization

Only after all components use semantic tokens, adjust the built-in dark theme toward VS Code Dark Modern / Dark+.

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
