#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=== Building Android File Manager for macOS Apple Silicon ==="

# 1. Clean previous build artifacts
rm -rf build dist

# 2. Locate pyinstaller
if [ -f ".venv/bin/pyinstaller" ]; then
    PYINSTALLER=".venv/bin/pyinstaller"
elif [ -f "venv/bin/pyinstaller" ]; then
    PYINSTALLER="venv/bin/pyinstaller"
elif command -v pyinstaller >/dev/null 2>&1; then
    PYINSTALLER="pyinstaller"
else
    echo "Error: PyInstaller not found."
    echo "Please activate your virtual environment or run: pip install -r requirements.txt"
    exit 1
fi

# 3. Run PyInstaller
echo "Using PyInstaller: $PYINSTALLER"
"$PYINSTALLER" \
    --noconfirm \
    --windowed \
    --name "Android File Manager" \
    --icon "AppIcon.icns" \
    --add-data "AppIcon.icns:." \
    --add-data "app_icon.png:." \
    --osx-bundle-identifier "com.androidfilemanager.macos" \
    --target-arch "arm64" \
    main.py

echo "Build completed in dist/"

APP_SOURCE="dist/Android File Manager.app"
DESKTOP_DEST="$HOME/Desktop/Android File Manager.app"

if [ -d "$APP_SOURCE" ]; then
    echo "Installing application bundle to Desktop: $DESKTOP_DEST"
    rm -rf "$DESKTOP_DEST"
    cp -R "$APP_SOURCE" "$DESKTOP_DEST"
    
    # Clean up intermediate build and dist directories to avoid duplicate app in Launchpad/Spotlight
    echo "Cleaning intermediate build/dist directories to prevent duplicates in Launchpad..."
    /System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister -u "$APP_SOURCE" 2>/dev/null || true
    rm -rf build dist
    
    # Register the single Desktop app with LaunchServices
    touch "$DESKTOP_DEST"
    /System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister -f "$DESKTOP_DEST" 2>/dev/null || true
    
    echo "=== Standalone .app bundle successfully installed to Desktop (no duplicates)! ==="
else
    echo "Error: Application bundle not found at $APP_SOURCE"
    exit 1
fi
