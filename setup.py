from setuptools import setup

APP = ['main.py']

DATA_FILES = [
    ('media', [
        'media/hattrix.png',
        'media/muted.png',
        'media/mic_open.png',
        'media/mute.mp3',
        'media/unmute.mp3'
    ])
]

OPTIONS = {
    'argv_emulation': False,
    'includes': ['PyObjCTools'],
    'packages': ['rumps'],
    # ADD THIS LINE: Exclude build tools that confuse py2app
    'excludes': ['packaging', 'setuptools', 'pip', 'wheel', 'installer'],

    'plist': {
        'CFBundleName': 'Hattrix',
        'CFBundleDisplayName': 'Hattrix',
        'CFBundleIdentifier': 'com.malaber.hattrix',
        'LSUIElement': True,
        'NSMicrophoneUsageDescription': 'Hattrix needs microphone access to toggle mute.',
        'NSAppleEventsUsageDescription': 'Hattrix needs to control Teams.',
    },
    'iconfile': 'media/hattrix.icns',
}

setup(
    app=APP,
    name='Hattrix',
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
)