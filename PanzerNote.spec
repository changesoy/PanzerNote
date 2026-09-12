# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

# ── C3-D: WebView2（PyWinRT）运行时收集 ─────────────────────────────
# webview2 / winrt 都是命名空间包（顶层无 __init__.py），且它们的原生文件是
# **包内数据**：webview2/_webview2_*.pyd、webview2/.../Microsoft.Web.WebView2.Core.dll、
# winrt/_winrt*.pyd、winrt/msvcp140.dll。PyInstaller 不会自动收集包内数据，
# 漏收集在真机上表现为「预览不可用」——必须显式收集，并保留包内相对目录
# （winrt-runtime 按包内路径查找并加载 Core DLL）。
_hidden_imports = (
    collect_submodules('webview2', on_error='ignore')
    + collect_submodules('winrt', on_error='ignore')
)
_extra_binaries = (
    collect_dynamic_libs('webview2') + collect_dynamic_libs('winrt')
)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_extra_binaries,
    datas=[('data', 'data'), ('themes', 'themes'), ('plugins', 'plugins')],
    hiddenimports=_hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# ── Qt translations 裁剪 ────────────────────────────────────
# 只保留中文(zh_CN)与英文(en)，其余语言全部删除。
# datas 项为 (dest, src, typecode) 三元组，dest 用反斜杠分隔。
def _keep_translation(dest: str) -> bool:
    normalized = dest.replace('\\', '/')
    if '/translations/' not in normalized:
        return True
    base = normalized.rsplit('/', 1)[-1]
    return base.endswith('_zh_CN.qm') or base.endswith('_en.qm')


a.datas = [d for d in a.datas if _keep_translation(d[0])]

# ── 运行期状态剔除 ──────────────────────────────────────────
# data/gamedata/savegame.json 是运行期存档：SavegameManager.load() 在文件缺失时
# 会自动创建，开发机跑一次应用就会在工作区生成。datas 里的 ('data', 'data') 是
# 整体收集，不加处理会把它打进发行包；而首跑向导（first_run_dialog）又会把
# data/gamedata 下的文件整体复制到用户数据目录 → 用户开局即继承开发机的资源数值
# 与当日签到状态。故打包一律剔除（同目录的 characters.json / secretary_lines.json
# 是随包数据，必须保留）。
_RUNTIME_STATE_FILES = {'data/gamedata/savegame.json'}


def _is_runtime_state(dest: str) -> bool:
    return dest.replace('\\', '/') in _RUNTIME_STATE_FILES


a.datas = [
    d for d in a.datas
    if _keep_translation(d[0]) and not _is_runtime_state(d[0])
]

# 注：B 分支遗留的 QML / Quick3D / Multimedia DLL 裁剪与 WebEngine debug 资源
# （*.debug.pak / *.debug.bin）过滤已随 C3-D 删除：那些条目是 PyQt6-WebEngine
# 的导入链把 QML 插件带进包才需要裁剪的。摘除该依赖后本应用不导入任何 QML，
# 实测冻结产物中 PyQt6/Qt6/qml 目录与那批 DLL 均不再被收集，保留过滤只会成为
# 永不命中的死代码。若将来重新引入 QML 依赖，需按当时产物重新评估裁剪清单。

# ── Qt6/bin 单文件裁剪：软件 OpenGL 兜底渲染器 ───────────────
# opengl32sw.dll（19.7 MB）是 Qt 的软件 OpenGL 兜底渲染器。本应用只有 QtWidgets
# （光栅绘制，不建 GL 上下文），C3-D 后预览也不再由 Qt 渲染，故不需要它。
# PyQt6 的 hook 默认会收集这个 DLL —— 实测剔除规则后产物体积立刻多出 19.7 MB。
_DROP_BIN_DLL = frozenset({"opengl32sw.dll"})


def _keep_bin_dll(dest: str) -> bool:
    normalized = dest.replace('\\', '/')
    if not (normalized.endswith('.dll') and '/Qt6/bin/' in normalized):
        return True
    return normalized.rsplit('/', 1)[-1].lower() not in _DROP_BIN_DLL


a.binaries = [b for b in a.binaries if _keep_bin_dll(b[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PanzerNote',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['data/assets/icons/app_icon.png'],
    contents_directory='.',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PanzerNote',
)
