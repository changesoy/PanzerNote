# -*- mode: python ; coding: utf-8 -*-
"""PanzerNote 打包规格（方案 A：轻量渲染，无 WebEngine）。

与方案 B 的同名规格（均为 PyInstaller 单目录模式）差异：
- A 已摘除 PyQt6-WebEngine，PyInstaller 分析阶段不再收集 `Qt6/qml` 整树与
  WebEngine 运行时（实测分析 toc 中 qml 记录为 0），因此不需要 B 的 QML 保留
  清单与 WebEngine debug 资源裁剪。
两分支共用的裁剪：
- Qt 翻译只保留中文(zh_CN)与英文(en)；
- 删除软件 OpenGL 兜底库 `opengl32sw.dll`（原为 WebEngine 无 GPU 时的软渲染兜底；
  A 无任何 OpenGL/QML 消费者，Qt Widgets 走光栅绘制）。
"""

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('data', 'data'), ('themes', 'themes'), ('plugins', 'plugins')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)


# ── A5-1: Qt translations 裁剪 ──────────────────────────────
# 只保留中文(zh_CN)与英文(en)，其余语言全部删除。
# datas 项为 (dest, src, typecode) 三元组，dest 用反斜杠分隔。
def _keep_translation(dest: str) -> bool:
    normalized = dest.replace('\\', '/')
    if '/translations/' not in normalized:
        return True
    base = normalized.rsplit('/', 1)[-1]
    return base.endswith('_zh_CN.qm') or base.endswith('_en.qm')


a.datas = [d for d in a.datas if _keep_translation(d[0])]


# ── A5-2: 软件 OpenGL 兜底库裁剪 ────────────────────────────
# 由 hook-PyQt6.QtGui 无条件收集（约 20 MB）。仅当需要软件 GL 兜底时才会被加载，
# A 无 WebEngine/OpenGL 消费者 → 可删；删后需真机 smoke 复核界面与预览渲染。
def _keep_gl_fallback(dest: str) -> bool:
    return not dest.replace('\\', '/').endswith('/opengl32sw.dll')


a.datas = [d for d in a.datas if _keep_gl_fallback(d[0])]
a.binaries = [b for b in a.binaries if _keep_gl_fallback(b[0])]


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
