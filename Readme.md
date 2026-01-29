# Hattrix 🎩

![GitHub release (latest by date)](https://img.shields.io/github/v/release/Malaber/hattrix?style=flat-square)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey?style=flat-square)

**Hattrix** is a native macOS menu bar utility that bridges the gap between your System Audio, AirPods, and Microsoft Teams. It ensures your "Mute" status is always in sync, no matter where you toggle it.

## ✨ Features

* **Global Sync:** Toggling mute on your system (keyboard F-keys) updates the icon instantly.
* **AirPods Integration:** Detects when you tap your AirPods to mute and updates the system/Teams status immediately.
* **Visual Confidence:** Always know if you are live or muted via the menu bar icon.
* **Teams Control:** * Includes a "Hang Up" shortcut.
    * Brings the Teams window to focus.

## 🚀 Installation

### Option 1: Homebrew (Recommended)
The easiest way to install and keep Hattrix updated is via Homebrew.

```bash
brew install --cask Malaber/tap/hattrix
```

### Option 2: build it yourself
Build the app from source:

```bash
pip install -r requirements.txt
rm -rf build dist
python setup.py py2app
```

The app can now be found in the `dist` folder.
