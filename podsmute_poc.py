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

# --- ctypes setup for CoreFoundation ---

# Load CoreFoundation framework
_cf = ctypes.CDLL(ctypes.util.find_library('CoreFoundation'))

# Define CoreFoundation types (simplified for our needs)
CFAllocatorRef = ctypes.c_void_p
CFNotificationCenterRef = ctypes.c_void_p
CFStringRef = ctypes.c_void_p
CFDictionaryRef = ctypes.c_void_p
CFIndex = ctypes.c_long
CFNotificationSuspensionBehavior = CFIndex
CFStringEncoding = ctypes.c_uint32

# CoreFoundation constants
kCFAllocatorDefault = CFAllocatorRef(0)
kCFStringEncodingUTF8 = CFStringEncoding(0x08000100)  # Defined in CoreFoundation/CFString.h

# Function prototypes for CFNotificationCenter functions
_cf.CFNotificationCenterGetDarwinNotifyCenter.argtypes = []
_cf.CFNotificationCenterGetDarwinNotifyCenter.restype = CFNotificationCenterRef

# CFStringCreateWithCString
_cf.CFStringCreateWithCString.argtypes = [CFAllocatorRef, ctypes.c_char_p, CFStringEncoding]
_cf.CFStringCreateWithCString.restype = CFStringRef

# Callback function prototype
# typedef void (*CFNotificationCallback)(
#   CFNotificationCenterRef center,
#   void *observer,
#   CFStringRef name,
#   const void *object,
#   CFDictionaryRef userInfo
# );
CFNotificationCallback = ctypes.CFUNCTYPE(
    None,  # restype (void)
    CFNotificationCenterRef,  # center
    ctypes.py_object,  # observer (we'll pass a py_object)
    CFStringRef,  # name
    ctypes.c_void_p,  # object
    CFDictionaryRef  # userInfo
)

_cf.CFNotificationCenterAddObserver.argtypes = [
    CFNotificationCenterRef,
    ctypes.py_object,  # observer (Python object)
    CFNotificationCallback,  # callback
    CFStringRef,  # name
    ctypes.c_void_p,  # object
    CFNotificationSuspensionBehavior  # suspensionBehavior
]
_cf.CFNotificationCenterAddObserver.restype = None

# We also need CFRelease for cleanup, though not critical for this POC
_cf.CFRelease.argtypes = [ctypes.c_void_p]
_cf.CFRelease.restype = None

_cf.CFNotificationCenterRemoveEveryObserver.argtypes = [
    CFNotificationCenterRef,
    ctypes.py_object,  # observer (Python object)
]
_cf.CFNotificationCenterRemoveEveryObserver.restype = None


# --- Global callback function ---
# This will be passed to CFNotificationCenterAddObserver via ctypes.
# It must match the CFUNCTYPE signature.
def _notification_callback_c(center, app_instance, name, object, user_info):
    """
    This C-compatible function is called by the system.
    'app_instance' should now directly be the AirPodsMuteApp instance passed from ctypes.
    """
    try:
        # Set a flag that the main thread's timer can safely read.
        app_instance.mute_event_received = True
    except Exception as e:
        # Log errors from background threads.
        print(f"Error in background callback (ctypes): {e}")


# Create the ctypes callback pointer
CTYPES_CALLBACK = CFNotificationCallback(_notification_callback_c)


class AirPodsMuteApp(rumps.App):
    def __init__(self):
        super(AirPodsMuteApp, self).__init__("AirPods Mute POC")
        self.title = ICON_UNMUTED
        self.muted = False
        self.mute_event_received = False
        self.listener_thread = None
        self.run_loop = None

        self.start_listener()

    def start_listener(self):
        """Set up and start the Darwin notification listener in a background thread."""
        self.listener_thread = threading.Thread(target=self.run_listener)
        self.listener_thread.daemon = True
        self.listener_thread.start()

    def run_listener(self):
        """The target for the background thread which will receive notifications."""
        self.run_loop = CFRunLoopGetCurrent()

        # Create CFStringRef for the notification name
        cf_notification_name = _cf.CFStringCreateWithCString(
            kCFAllocatorDefault,
            MUTE_NOTIFICATION_BYTES,
            kCFStringEncodingUTF8
        )

        _cf.CFNotificationCenterAddObserver(
            _cf.CFNotificationCenterGetDarwinNotifyCenter(),
            self,  # Pass 'self' (the Python app instance) directly as observer context.
            CTYPES_CALLBACK,  # Pass the ctypes callback pointer.
            cf_notification_name,  # Notification name as CFStringRef
            None,  # object (no filtering)
            0,  # suspensionBehavior (deliverImmediately)
        )

        # It's good practice to release CFStringRef when done.
        # However, for a static, app-lifetime string, it's often acceptable
        # to omit for simplicity in a POC as it cleans up on app exit.
        # _cf.CFRelease(cf_notification_name) # Will keep it for now.

        # This run loop will now block and wait for notifications.
        CFRunLoopRun()

    @rumps.timer(0.2)
    def check_for_event(self, _):
        """On the main thread, check for the flag set by the background thread."""
        if self.mute_event_received:
            self.muted = not self.muted
            self.title = ICON_MUTED if self.muted else ICON_UNMUTED
            self.mute_event_received = False  # Reset the flag

    @rumps.clicked("Quit")
    def quit_app(self, _):
        """Cleanly stop the listener thread and quit."""
        if self.run_loop:
            # Recreate CFStringRef for removal
            cf_notification_name = _cf.CFStringCreateWithCString(
                kCFAllocatorDefault,
                MUTE_NOTIFICATION_BYTES,
                kCFStringEncodingUTF8
            )
            _cf.CFNotificationCenterRemoveEveryObserver(
                _cf.CFNotificationCenterGetDarwinNotifyCenter(),
                self,
                cf_notification_name  # The name must match the one used for adding
            )
            _cf.CFRelease(cf_notification_name)  # Release after use

            CFRunLoopStop(self.run_loop)
        rumps.quit_application()


if __name__ == "__main__":
    print("Starting AirPods Mute POC.")
    print("Final attempt with robust ctypes CFString handling.")
    print("Press the mute button on your AirPods to toggle the icon.")
    AirPodsMuteApp().run()
