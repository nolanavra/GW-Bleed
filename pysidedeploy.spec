[app]
title = GW Bleed Internal Alpha
project_dir = .
input_file = desktop.py
exec_directory = build/standalone
project_file =
icon =

[python]
python_path = .venv/Scripts/python.exe
packages = Nuitka==4.1.1
android_packages =

[qt]
qml_files =
excluded_qml_plugins =
modules = Core,Gui,Widgets,Svg,SvgWidgets
plugins = platforms,styles,imageformats

[nuitka]
mode = standalone
extra_args = --msvc=latest --assume-yes-for-downloads --include-package=gw_imposition --include-data-dir=gw_imposition/resources=gw_imposition/resources --include-package-data=pypdfium2 --include-package-data=pypdfium2_raw --windows-console-mode=attach --noinclude-qt-translations --nofollow-import-to=reportlab,pytest,zxingcpp --output-filename=GW-Bleed-Alpha.exe --report=build/nuitka-report.xml
