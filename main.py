import os
import rumps
import subprocess
from AppKit import NSStatusBar, NSVariableStatusItemLength

# --- Imports for AirPods detection ---
import threading
import ctypes
import ctypes.util
from CoreFoundation import CFRunLoopGetCurrent, CFRunLoopRun, CFRunLoopStop

# --- CONFIGURATION ---
TEAMS_PROCESS_NAME = "Microsoft Teams"
MUTE_NOTIFICATION_BYTES = b"com.apple.audioaccessoryd.MuteState"

# ICONS
ICON_MUTED = "🔴"
ICON_LIVE = "🟢"
ICON_MENU = "⚙️"  # The icon for the menu button

# SOUNDS
SOUND_ON_MUTE = "media/mute.mp3"
SOUND_ON_UNMUTE = "media/unmute.mp3"


# --- Ctypes / CoreFoundation Setup for AirPods mute detection ---
class CFBridge:
    _cf = ctypes.CDLL(ctypes.util.find_library('CoreFoundation'))

    # Types
    CFAllocatorRef = ctypes.c_void_p
    CFNotificationCenterRef = ctypes.c_void_p
    CFStringRef = ctypes.c_void_p
    CFDictionaryRef = ctypes.c_void_p
    CFIndex = ctypes.c_long
    CFNotificationSuspensionBehavior = CFIndex
    CFStringEncoding = ctypes.c_uint32

    # Constants
    kCFAllocatorDefault = CFAllocatorRef(0)
    kCFStringEncodingUTF8 = CFStringEncoding(0x08000100)

    # Functions
    GetDarwinNotifyCenter = _cf.CFNotificationCenterGetDarwinNotifyCenter
    GetDarwinNotifyCenter.restype = CFNotificationCenterRef

    StringCreateWithCString = _cf.CFStringCreateWithCString
    StringCreateWithCString.argtypes = [CFAllocatorRef, ctypes.c_char_p, CFStringEncoding]
    StringCreateWithCString.restype = CFStringRef

    Release = _cf.CFRelease
    Release.argtypes = [ctypes.c_void_p]

    # Callback Definition
    CFNotificationCallback = ctypes.CFUNCTYPE(
        None, CFNotificationCenterRef, ctypes.py_object, CFStringRef, ctypes.c_void_p, CFDictionaryRef
    )

    AddObserver = _cf.CFNotificationCenterAddObserver
    AddObserver.argtypes = [
        CFNotificationCenterRef, ctypes.py_object, CFNotificationCallback,
        CFStringRef, ctypes.c_void_p, CFNotificationSuspensionBehavior
    ]

    RemoveObserver = _cf.CFNotificationCenterRemoveObserver
    RemoveObserver.argtypes = [
        CFNotificationCenterRef, ctypes.py_object, CFStringRef, ctypes.c_void_p
    ]


# --- Global Callback ---
def _notification_callback_c(center, app_instance, name, object, user_info):
    """Called from the background C-thread. Signal the app instance."""
    if app_instance:
        app_instance.mute_event_received = True

# Create the C-callable function pointer once
CTYPES_CALLBACK = CFBridge.CFNotificationCallback(_notification_callback_c)


class SplitTeamsController(rumps.App):
    def __init__(self):
        # 1. SETUP THE MENU APP (The Gear Icon)
        super(SplitTeamsController, self).__init__("TeamsMenu", icon=None, title=ICON_MENU)

        self.is_muted = self.check_system_mute_status()

        # --- State for AirPods listener ---
        self.mute_event_received = False
        self.listener_thread = None
        self.run_loop = None
        self.cf_notification_name = None

        # Create the CFString ONCE and reuse it
        self.cf_notification_name = CFBridge.StringCreateWithCString(
            CFBridge.kCFAllocatorDefault,
            MUTE_NOTIFICATION_BYTES,
            CFBridge.kCFStringEncodingUTF8
        )
        self.start_listener()

        # Menu Items
        self.menu = [
            rumps.MenuItem("Auflegen (Hang Up)", callback=self.hang_up),
            rumps.MenuItem("Teams zeigen (Focus)", callback=self.show_window),
            None,
            rumps.MenuItem("Beenden", callback=self.quit_app)
        ]

        # 2. SETUP THE SECOND ICON (The Mic Toggle)
        # We have to use native macOS calls (AppKit) to add a second item to the bar
        self.statusbar = NSStatusBar.systemStatusBar()
        self.mic_item = self.statusbar.statusItemWithLength_(NSVariableStatusItemLength)
        self.mic_item.button().setTitle_(ICON_MUTED if self.is_muted else ICON_LIVE)

        # Assign the click action to the 'quick_toggle' function
        self.mic_item.button().setTarget_(self)
        self.mic_item.button().setAction_("quickToggle:")

    # --- AirPods Event Listener ---
    def start_listener(self):
        self.listener_thread = threading.Thread(target=self.run_listener)
        self.listener_thread.daemon = True
        self.listener_thread.start()

    def run_listener(self):
        """Background thread loop."""
        self.run_loop = CFRunLoopGetCurrent()

        CFBridge.AddObserver(
            CFBridge.GetDarwinNotifyCenter(),
            self,  # Observer context
            CTYPES_CALLBACK,  # Callback
            self.cf_notification_name,
            None,
            0  # Deliver Immediately
        )
        CFRunLoopRun()

    @rumps.timer(0.1)
    def check_for_event(self, _):
        """Main thread timer checks for the flag from the background thread."""
        if self.mute_event_received:
            self.toggle_mute()
            self.mute_event_received = False  # Reset flag

    # --- ACTION HANDLER FOR THE MIC BUTTON ---
    # This weird signature is required for native button clicks
    def quickToggle_(self, sender):
        self.toggle_mute()

    # --- CORE LOGIC ---
    def toggle_mute(self):
        if self.is_muted:
            self.unmute_system()
        else:
            self.mute_system()

        self.sync_state()

    def hang_up(self, _):
        script = f'''
        tell application "{TEAMS_PROCESS_NAME}" to activate
        tell application "System Events" to keystroke "h" using {{command down, shift down}}
        '''
        subprocess.run(["osascript", "-e", script])
        self.sync_state()

    def show_window(self, _):
        script = f'tell application "{TEAMS_PROCESS_NAME}" to activate'
        subprocess.run(["osascript", "-e", script])

    def sync_state(self):
        # Update logic
        self.is_muted = self.check_system_mute_status()

        # Update the visual icon of the Second Button
        self.mic_item.button().setTitle_(ICON_MUTED if self.is_muted else ICON_LIVE)

    # --- AUDIO CONTROL & FEEDBACK ---
    def play_feedback_sound(self, sound_path):
        """Plays a sound asynchronously if it exists."""
        if os.path.exists(sound_path):
            subprocess.Popen(["afplay", sound_path])

    def mute_system(self):
        subprocess.run(["osascript", "-e", "set volume input volume 0"])
        self.play_feedback_sound(SOUND_ON_MUTE)

    def unmute_system(self):
        subprocess.run(["osascript", "-e", "set volume input volume 100"])
        self.play_feedback_sound(SOUND_ON_UNMUTE)

    def check_system_mute_status(self):
        script = "input volume of (get volume settings)"
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True).stdout.strip()
        try:
            return int(result) == 0
        except ValueError:
            return False

    def quit_app(self, _=None):
        """Cleanly shut down the listener before quitting."""
        if self.run_loop:
            CFBridge.RemoveObserver(
                CFBridge.GetDarwinNotifyCenter(),
                self,
                self.cf_notification_name,
                None
            )
            CFRunLoopStop(self.run_loop)

        if self.cf_notification_name:
            CFBridge.Release(self.cf_notification_name)

        rumps.quit_application()


if __name__ == "__main__":
    SplitTeamsController().run()
