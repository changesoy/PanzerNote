# -*- mode: python ; coding: utf-8 -*-

import os

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
# ── B2-1: Qt translations 裁剪 ──────────────────────────────
# 只保留中文(zh_CN)与英文(en)，其余语言全部删除。
# datas 项为 (dest, src, typecode) 三元组，dest 用反斜杠分隔。
def _keep_translation(dest: str) -> bool:
    normalized = dest.replace('\\', '/')
    if '/translations/' not in normalized:
        return True
    base = normalized.rsplit('/', 1)[-1]
    return base.endswith('_zh_CN.qm') or base.endswith('_en.qm')


a.datas = [d for d in a.datas if _keep_translation(d[0])]

# ── B2-2: 删除 WebEngine debug 资源 ──────────────────────────
# *.debug.pak / *.debug.bin（devtools 及 v8 调试快照），release 运行不需要。
a.datas = [d for d in a.datas if '.debug.pak' not in d[0] and '.debug.bin' not in d[0]]

# ── B2-3: qml 目录裁剪 + 联动 bin DLL 裁剪 ───────────────────
# 只保留 WebEngine 运行必需的 QML 模块：QtQml / QtQuick / QtWebEngine，
# 其余 QML 模块（Multimedia/Quick3D/Sensors/Test 等）随其插件 DLL 一并删除。
_QML_KEEP_TOP = frozenset({"QtQml", "QtQuick", "QtWebEngine"})

# bin 中仅被"已删 qml 插件"引用的 DLL（探针实测零保留根引用，可安全删除）
_DROP_BIN_DLL = frozenset({
    "qt6multimedia.dll", "qt6multimediaquick.dll", "qt6positioningquick.dll",
    "qt6quick3d.dll", "qt6quick3dassetimport.dll", "qt6quick3dassetutils.dll",
    "qt6quick3deffects.dll", "qt6quick3dhelpers.dll", "qt6quick3dhelpersimpl.dll",
    "qt6quick3dparticles.dll", "qt6quick3dphysics.dll", "qt6quick3dphysicshelpers.dll",
    "qt6quick3druntimerender.dll", "qt6quick3dspatialaudio.dll", "qt6quick3dutils.dll",
    "qt6quick3dxr.dll", "qt6quicktest.dll", "qt6remoteobjects.dll",
    "qt6remoteobjectsqml.dll", "qt6sensors.dll", "qt6sensorsquick.dll",
    "qt6serialport.dll", "qt6shadertools.dll", "qt6spatialaudio.dll",
    "qt6test.dll", "qt6texttospeech.dll", "qt6websockets.dll",
    # B2-4: 软件 OpenGL 渲染器（WebEngine 无 GPU 时的兜底软渲染）。
    # 目标机有正常 GPU 驱动时不需要；删除后需真机验证预览渲染。
    "opengl32sw.dll",
})


def _keep_qml(dest: str) -> bool:
    normalized = dest.replace('\\', '/')
    marker = '/Qt6/qml/'
    if marker not in normalized:
        return True
    top = normalized.split(marker, 1)[1].split('/')[0]
    return top in _QML_KEEP_TOP


def _keep_bin_dll(dest: str) -> bool:
    normalized = dest.replace('\\', '/')
    if not (normalized.endswith('.dll') and '/Qt6/bin/' in normalized):
        return True
    return os.path.basename(normalized).lower() not in _DROP_BIN_DLL


a.datas = [d for d in a.datas if _keep_qml(d[0])]
a.binaries = [b for b in a.binaries if _keep_qml(b[0])]
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
