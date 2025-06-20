# -- mode python ; coding utf-8 --

# PyInstaller spec file for Study Timer GUI

block_cipher = None

# 分析阶段：找到所有依赖和资源文件
a = Analysis(
    ['study_timer_gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('study_music', 'study_music'), # 关键：添加整个 'study_music' 文件夹
        ('icon.ico', '.')             # 关键：添加 'icon.ico' 文件到根目录
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 打包 Python 模块
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 创建可执行文件 (.exe)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='study_timer_gui',      # 生成的 .exe 文件名
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,              # 关键：设置为 False，因为它是一个 GUI 应用，不需要控制台窗口
    windowed=True,              # 同上
    icon='icon.ico',            # 关键：为 .exe 文件设置图标
)

# 收集所有文件到一个文件夹中（适用于 one-folder模式）
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='study_timer_gui',     # 最终在 dist 文件夹中生成的文件夹名称
)