import rumps
import threading
import ctypes
import ctypes.util
from CoreFoundation import (
    CFRunLoopGetCurrent,
    CFRunLoopRun,
    CFRunLoopStop,
)

# --- Configuration ---
MUTE_NOTIFICATION_BYTES = b"com.apple.audioaccessoryd.MuteState"
ICON_UNMUTED = "👂"
ICON_MUTED = "🤫"


# --- Ctypes / CoreFoundation Setup ---
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


class AirPodsMuteApp(rumps.App):
    def __init__(self):
        super(AirPodsMuteApp, self).__init__("AirPods Mute")
        self.title = ICON_UNMUTED
        self.muted = False
        self.mute_event_received = False

        self.listener_thread = None
        self.run_loop = None

        # Optimize: Create the CFString ONCE and reuse it
        self.cf_notification_name = CFBridge.StringCreateWithCString(
            CFBridge.kCFAllocatorDefault,
            MUTE_NOTIFICATION_BYTES,
            CFBridge.kCFStringEncodingUTF8
        )

        self.start_listener()

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
    def update_ui(self, _):
        """Main thread timer checks for the flag."""
        if self.mute_event_received:
            self.muted = not self.muted
            self.title = ICON_MUTED if self.muted else ICON_UNMUTED
            self.mute_event_received = False  # Reset flag

    @rumps.clicked("Quit")
    def quit_app(self, _):
        if self.run_loop:
            # Correct cleanup: Remove observer using the saved CFString and specific function
            CFBridge.RemoveObserver(
                CFBridge.GetDarwinNotifyCenter(),
                self,
                self.cf_notification_name,
                None
            )
            CFRunLoopStop(self.run_loop)

        # Release memory
        if self.cf_notification_name:
            CFBridge.Release(self.cf_notification_name)

        rumps.quit_application()


if __name__ == "__main__":
    print("Starting AirPods Mute POC (Streamlined).")
    AirPodsMuteApp().run()
