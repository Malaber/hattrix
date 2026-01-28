import rumps
import subprocess
from AppKit import NSStatusBar, NSVariableStatusItemLength, NSImage, NSSound
from Foundation import NSSize, NSAppleScript

# --- Imports for AirPods detection ---
import threading
import ctypes
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
    """Called from the background C-thread. Signal the app instance."""
    if app_instance:
        app_instance.mute_event_received = True

# Create the C-callable function pointer once
CTYPES_CALLBACK = CFBridge.CFNotificationCallback(_notification_callback_c)


class SplitTeamsController(rumps.App):
    def __init__(self):
        # 1. SETUP THE MENU APP (The Gear Icon)
        super(SplitTeamsController, self).__init__("TeamsMenu", icon=ICON_MENU_PATH, title=None)

        # Optimization: Pre-compile AppleScript for volume checking
        # This keeps the script compilation in memory rather than re-reading it every second
        self.check_vol_script = NSAppleScript.alloc().initWithSource_("input volume of (get volume settings)")

        # Optimization: Pre-load Sounds
        self.sound_mute = NSSound.alloc().initWithContentsOfFile_byReference_(SOUND_ON_MUTE, True)
        self.sound_unmute = NSSound.alloc().initWithContentsOfFile_byReference_(SOUND_ON_UNMUTE, True)

        self.is_muted = self.check_system_mute_status()

        # --- Load Template Images ---
        self.image_muted = NSImage.alloc().initWithContentsOfFile_(ICON_MUTED_PATH)
        self.image_muted.setTemplate_(True)
        self.image_muted.setSize_(NSSize(18, 18))

        self.image_live = NSImage.alloc().initWithContentsOfFile_(ICON_LIVE_PATH)
        self.image_live.setTemplate_(True)
        self.image_live.setSize_(NSSize(18, 18))

        # --- State for AirPods listener ---
        self.mute_event_received = False
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

    # --- AirPods Event Listener ---
    def start_listener(self):
        self.listener_thread = threading.Thread(target=self.run_listener)
        self.listener_thread.daemon = True
        self.listener_thread.start()

    def run_listener(self):
        """Background thread loop."""
        self.run_loop = CFRunLoopGetCurrent()
        CFBridge.AddObserver(CFBridge.GetDarwinNotifyCenter(), self, CTYPES_CALLBACK, self.cf_notification_name, None,
                             0)
        CFRunLoopRun()

    @rumps.timer(2)
    def poll_for_changes(self, _):
        """Main thread timer checks for the flag from the background thread and external mute changes."""
        # 1. Check for AirPods button press
        if self.mute_event_received:
            self.toggle_mute()
            self.mute_event_received = False  # Reset flag
            # After toggling, the state is already synced, so we can return
            return

        # 2. Lower priority: Check system state
        current_system_mute_status = self.check_system_mute_status()
        if current_system_mute_status != self.is_muted:
            self.sync_state()

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
        self.mic_item.button().setImage_(self.image_muted if self.is_muted else self.image_live)

    # --- AUDIO CONTROL & FEEDBACK ---
    def play_feedback_sound(self, sound_obj):
        """Plays using native NSSound"""
        if sound_obj:
            sound_obj.stop()  # Stop if currently playing
            sound_obj.play()

    def mute_system(self):
        subprocess.run(["osascript", "-e", "set volume input volume 0"])
        self.play_feedback_sound(self.sound_mute)

    def unmute_system(self):
        subprocess.run(["osascript", "-e", "set volume input volume 100"])
        self.play_feedback_sound(self.sound_unmute)

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
