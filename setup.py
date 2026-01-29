from setuptools import setup

APP = ['your_main_script.py'] # Replace with your actual .py filename
DATA_FILES = ['media']
OPTIONS = {
    'argv_emulation': True,
    'plist': {
        'CFBundleName': 'Hattrix',
        'CFBundleDisplayName': 'Hattrix',
        'CFBundleIdentifier': 'com.yourname.hattrix',
        'CFBundleVersion': '1.0.0',
        'LSUIElement': True,
        'NSMicrophoneUsageDescription': 'Hattrix needs microphone access to sync your Teams mute status.',
    },
    'packages': ['rumps', 'AppKit', 'Foundation', 'ctypes'],
    'iconfile': 'media/hattrix.icns',
}

setup(
    app=APP,
    name='Hattrix',
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
