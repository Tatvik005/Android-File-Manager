#!/usr/bin/env bash
# ==============================================================================
# setup_new_mac.sh
# One-click automated setup script for Android File Manager on your new Mac.
# ==============================================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=================================================================="
echo "    Android File Manager - New Mac Automatic Setup & Installer   "
echo "=================================================================="
echo ""

# ------------------------------------------------------------------------------
# 1. Check & Install Homebrew
# ------------------------------------------------------------------------------
echo "[1/5] Checking Homebrew..."
if command -v brew >/dev/null 2>&1; then
    echo "  ✓ Homebrew is already installed: $(which brew)"
else
    echo "  ! Homebrew is not installed. Installing Homebrew now..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    
    # Add Homebrew to PATH for Apple Silicon if needed
    if [ -f "/opt/homebrew/bin/brew" ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
fi

# ------------------------------------------------------------------------------
# 2. Check & Install Android Debug Bridge (ADB)
# ------------------------------------------------------------------------------
echo ""
echo "[2/5] Checking Android Debug Bridge (ADB)..."
if command -v adb >/dev/null 2>&1; then
    echo "  ✓ ADB is already installed: $(adb --version | head -n 1)"
else
    echo "  ! ADB not found. Installing android-platform-tools via Homebrew..."
    brew install android-platform-tools
    echo "  ✓ ADB installed successfully: $(adb --version | head -n 1)"
fi

# ------------------------------------------------------------------------------
# 3. Fix macOS Gatekeeper Quarantine on the .app bundle
# ------------------------------------------------------------------------------
echo ""
echo "[3/5] Configuring Standalone .app Bundle..."
APP_BUNDLE="Android File Manager.app"

if [ -d "$APP_BUNDLE" ]; then
    echo "  Removing macOS quarantine attributes (prevents 'App is damaged' warning)..."
    xattr -cr "$APP_BUNDLE" 2>/dev/null || true
    chmod +x "$APP_BUNDLE/Contents/MacOS/Android File Manager" 2>/dev/null || true
    
    # Ask where to install the app
    echo ""
    echo "  Where would you like to install Android File Manager?"
    echo "    1) Applications folder (/Applications/Android File Manager.app) [Recommended]"
    echo "    2) Desktop (~/Desktop/Android File Manager.app)"
    echo "    3) Leave it in this folder"
    read -p "  Enter choice [1, 2, or 3] (default: 1): " INSTALL_CHOICE
    INSTALL_CHOICE=${INSTALL_CHOICE:-1}
    
    if [ "$INSTALL_CHOICE" = "1" ]; then
        DEST="/Applications/Android File Manager.app"
        echo "  Copying to $DEST..."
        rm -rf "$DEST"
        cp -R "$APP_BUNDLE" "$DEST"
        xattr -cr "$DEST" 2>/dev/null || true
        /System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister -f "$DEST" 2>/dev/null || true
        echo "  ✓ App successfully installed to /Applications!"
        TARGET_TO_LAUNCH="$DEST"
    elif [ "$INSTALL_CHOICE" = "2" ]; then
        DEST="$HOME/Desktop/Android File Manager.app"
        echo "  Copying to $DEST..."
        rm -rf "$DEST"
        cp -R "$APP_BUNDLE" "$DEST"
        xattr -cr "$DEST" 2>/dev/null || true
        /System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister -f "$DEST" 2>/dev/null || true
        echo "  ✓ App successfully installed to Desktop!"
        TARGET_TO_LAUNCH="$DEST"
    else
        echo "  Leaving app bundle in $DIR"
        TARGET_TO_LAUNCH="$DIR/$APP_BUNDLE"
    fi
else
    echo "  ! Precompiled .app not found in this folder. You can compile it anytime using ./build_app.sh"
fi

# ------------------------------------------------------------------------------
# 4. Optional: Set Up Python Development Environment
# ------------------------------------------------------------------------------
echo ""
echo "[4/5] Python Development Setup (Optional)..."
read -p "  Do you want to set up a Python virtual environment to run/modify from source? (y/N): " SETUP_VENV
if [[ "$SETUP_VENV" =~ ^[Yy]$ ]]; then
    if command -v python3 >/dev/null 2>&1; then
        echo "  Creating virtual environment in .venv..."
        python3 -m venv .venv
        echo "  Installing dependencies from requirements.txt..."
        .venv/bin/pip install --upgrade pip
        .venv/bin/pip install -r requirements.txt
        echo "  ✓ Python virtual environment ready! Run with: .venv/bin/python main.py"
    else
        echo "  ! python3 command not found. Please install Python 3.10+ to run from source."
    fi
else
    echo "  Skipping Python environment setup."
fi

# ------------------------------------------------------------------------------
# 5. Launch Application
# ------------------------------------------------------------------------------
echo ""
echo "[5/5] Setup Complete!"
echo "=================================================================="
if [ -n "$TARGET_TO_LAUNCH" ] && [ -d "$TARGET_TO_LAUNCH" ]; then
    read -p "  Would you like to open Android File Manager now? (Y/n): " OPEN_APP
    OPEN_APP=${OPEN_APP:-Y}
    if [[ "$OPEN_APP" =~ ^[Yy]$ ]]; then
        open "$TARGET_TO_LAUNCH"
        echo "  ✓ Launched Android File Manager!"
    fi
fi

echo ""
echo "Done! Plug in your Android phone via USB (with USB Debugging ON) and enjoy!"
echo "For more details, see HOW_TO_INSTALL.txt"
echo "=================================================================="
