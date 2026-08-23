#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
package_root="$project_root/build/pps-designer-linux"
stage_root="$package_root/stage"

command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 2; }
command -v fpm >/dev/null 2>&1 || { echo "fpm is required to emit DEB and RPM packages" >&2; exit 2; }

python3 -m venv "$package_root/venv"
"$package_root/venv/bin/pip" install --upgrade pip
"$package_root/venv/bin/pip" install "$project_root[designer,package]"
"$package_root/venv/bin/pyinstaller" --noconfirm --clean \
  --name PPSDesigner --windowed --onedir \
  --collect-all webview \
  --collect-data peripersonal_space_toolkit \
  --exclude-module PySide6 --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module cefpython3 \
  "$project_root/apps/designer/launchers/designer_launcher_entry.py"

mkdir -p "$stage_root/usr/lib/pps-designer" "$stage_root/usr/bin" "$stage_root/usr/share/applications"
cp -R "$project_root/dist/PPSDesigner/." "$stage_root/usr/lib/pps-designer/"
cp "$project_root/packaging/linux/pps-designer.desktop" "$stage_root/usr/share/applications/pps-designer.desktop"
ln -sf ../lib/pps-designer/PPSDesigner "$stage_root/usr/bin/pps-designer"

for package_type in deb rpm; do
  fpm -s dir -t "$package_type" -n pps-experiment-designer -v 0.1.0 \
    --description "Cross-platform PPS Experiment Designer" \
    --depends "webkit2gtk" --depends "gtk3" \
    -C "$stage_root" -p "$package_root/pps-experiment-designer-0.1.0.x86_64.$package_type" .
done
