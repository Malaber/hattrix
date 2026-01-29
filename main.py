import rumps
import subprocess
from AppKit import NSStatusBar, NSVariableStatusItemLength, NSImage, NSSound
from Foundation import NSSize, NSAppleScript
from PyObjCTools import AppHelper  # <--- REQUIRED for instant background events

# --- Imports for AirPods detection ---
import threading
import ctypes.util
from CoreFoundation import CFRunLoopGetCurrent, CFRunLoopRun, CFRunLoopStop

# --- CONFIGURATION ---
TEAMS_PROCESS_NAME = "Microsoft Teams"
MUTE_NOTIFICATION_BYTES = b"com.apple.audioaccessoryd.MuteState"

# ICONS
ICON_MENU_PATH = "media/hattrix.png"
ICON_MUTED_PATH = "media/muted.png"
ICON_LIVE_PATH = "media/mic_open.png"

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
    CFNotificationCallback = ctypes.CFUNCTYPE(None, CFNotificationCenterRef, ctypes.py_object, CFStringRef,
                                              ctypes.c_void_p, CFDictionaryRef)
    AddObserver = _cf.CFNotificationCenterAddObserver
    AddObserver.argtypes = [CFNotificationCenterRef, ctypes.py_object, CFNotificationCallback, CFStringRef,
                            ctypes.c_void_p, CFNotificationSuspensionBehavior]
    RemoveObserver = _cf.CFNotificationCenterRemoveObserver
    RemoveObserver.argtypes = [CFNotificationCenterRef, ctypes.py_object, CFStringRef, ctypes.c_void_p]


# --- Global Callback ---
def _notification_callback_c(center, app_instance, name, object, user_info):
    """
    Called from the background thread when AirPods are clicked.
    We use AppHelper to INSTANTLY trigger the toggle on the Main Thread.
    """
    if app_instance:
        AppHelper.callAfter(app_instance.toggle_mute)

# Create the C-callable function pointer once
CTYPES_CALLBACK = CFBridge.CFNotificationCallback(_notification_callback_c)


class SplitTeamsController(rumps.App):
    def __init__(self):
        # 1. SETUP THE MENU APP (The Gear Icon)
        super(SplitTeamsController, self).__init__("TeamsMenu", icon=ICON_MENU_PATH, title=None, template=True)

        # Optimization: Pre-compile AppleScript for volume checking
        # This keeps the script compilation in memory rather than re-reading it every second
        self.check_vol_script = NSAppleScript.alloc().initWithSource_("input volume of (get volume settings)")

        # Optimization: Pre-load Sounds
        self.sound_mute = NSSound.alloc().initWithContentsOfFile_byReference_(SOUND_ON_MUTE, True)
        self.sound_unmute = NSSound.alloc().initWithContentsOfFile_byReference_(SOUND_ON_UNMUTE, True)

        self.is_muted = self.check_system_mute_status()

        # --- Load Secondary Images ---
        # We still use the helper for the second icon because we manage it manually
        self.image_muted = self._load_icon(ICON_MUTED_PATH)
        self.image_live = self._load_icon(ICON_LIVE_PATH)

        # --- State for AirPods listener ---
        self.listener_thread = None
        self.run_loop = None
        self.cf_notification_name = CFBridge.StringCreateWithCString(CFBridge.kCFAllocatorDefault,
                                                                     MUTE_NOTIFICATION_BYTES,
                                                                     CFBridge.kCFStringEncodingUTF8)

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
        self.mic_item.button().setImage_(self.image_muted if self.is_muted else self.image_live)

        # Assign the click action to the 'quick_toggle' function
        self.mic_item.button().setTarget_(self)
        self.mic_item.button().setAction_("quickToggle:")

    def _load_icon(self, path):
        """Helper to load an image, set it as a template, and resize it to 18x18."""
        image = NSImage.alloc().initWithContentsOfFile_(path)
        if image:
            image.setTemplate_(True)
            image.setSize_(NSSize(18, 18))
        return image

    # --- AirPods Event Listener ---
    def start_listener(self):
        self.listener_thread = threading.Thread(target=self.run_listener)
        self.listener_thread.daemon = True
        self.listener_thread.start()

    def run_listener(self):
        """Background thread loop."""
        self.run_loop = CFRunLoopGetCurrent()
        CFBridge.AddObserver(CFBridge.GetDarwinNotifyCenter(), self, CTYPES_CALLBACK, self.cf_notification_name, None, 0)
        CFRunLoopRun()

    @rumps.timer(10)
    def poll_for_changes(self, _):
        """
        Slow timer (10s) just to keep sync with external changes (like keyboard volume keys).
        The AirPods button does NOT wait for this timer anymore.
        """
        current_system_mute_status = self.check_system_mute_status()
        if current_system_mute_status != self.is_muted:
            self.sync_state()

    # --- ACTION HANDLER FOR THE MIC BUTTON ---
    # This weird signature is required for native button clicks
    def quickToggle_(self, sender):
        self.toggle_mute()

    # --- CORE LOGIC ---
    def toggle_mute(self):
        # 1. Update internal state from reality first.
        # This prevents desync if you muted via keyboard 0.5s ago and the timer hasn't caught it yet.
        self.is_muted = self.check_system_mute_status()

        # 2. Perform the toggle
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
        # Update internal variable
        self.is_muted = self.check_system_mute_status()
        # Update Icon for second button
        self.mic_item.button().setImage_(self.image_muted if self.is_muted else self.image_live)

    # --- NOTIFICATIONS ---
    def send_notification(self, title, subtitle, message):
        """Wrapper for rumps notifications."""
        rumps.notification(
            title=title,
            subtitle=subtitle,
            message=message,
            sound=False # We handle sound manually via NSSound for faster response
        )

    # --- AUDIO CONTROL ---
    def play_feedback_sound(self, sound_obj):
        """Plays using native NSSound"""
        if sound_obj:
            sound_obj.stop()  # Stop if currently playing
            sound_obj.play()

    def mute_system(self):
        subprocess.run(["osascript", "-e", "set volume input volume 0"])
        self.play_feedback_sound(self.sound_mute)
        self.send_notification("Microphone Muted", "System Input Volume: 0", "You are now muted.")

    def unmute_system(self):
        subprocess.run(["osascript", "-e", "set volume input volume 100"])
        self.play_feedback_sound(self.sound_unmute)
        self.send_notification("Microphone Live", "System Input Volume: 100", "You are now live!")

    def check_system_mute_status(self):
        """Uses NSAppleScript to avoid forking a process."""
        try:
            # executeAndReturnError_ returns (NSAppleEventDescriptor, error_dict)
            result_descriptor, error = self.check_vol_script.executeAndReturnError_(None)

            if error:
                return self.is_muted  # Fail safe

            # stringValue() gets the string result ("0", "100", etc)
            vol_str = result_descriptor.stringValue()
            return int(vol_str) == 0
        except:
            return False

    def quit_app(self, _=None):
        """Cleanly shut down the listener before quitting."""
        if self.run_loop:
            CFBridge.RemoveObserver(CFBridge.GetDarwinNotifyCenter(), self, self.cf_notification_name, None)
            CFRunLoopStop(self.run_loop)
        if self.cf_notification_name:
            CFBridge.Release(self.cf_notification_name)
        rumps.quit_application()


if __name__ == "__main__":
    SplitTeamsController().run()
