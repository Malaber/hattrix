# PodsMute POC: Darwin Notification Listener

This document explains the inner workings of `podsmute_poc.py`. The goal of this Proof-of-Concept (POC) is to provide a Python menu bar application that listens for the specific "mute" button press on AirPods and reacts to it using native macOS APIs.

## The Challenge: Listening to System Events

There is no standard Python API to detect the AirPods mute button press. This event is a private, low-level system notification broadcast by the macOS service `audioaccessoryd`.

The notification name is `com.apple.audioaccessoryd.MuteState`. It is a **Darwin Notification**—a system-wide, C-level inter-process communication mechanism. To capture this in Python, we must bypass standard libraries and bridge directly to the macOS `CoreFoundation` framework.

## The Solution: `ctypes` & `CFBridge`

The solution uses Python's `ctypes` library to interact with shared C libraries. To ensure code stability, readability, and memory safety, all low-level C interactions are encapsulated in a helper class named `CFBridge`.

### 1. The `CFBridge` Class
Instead of scattering C definitions globally, `CFBridge` acts as a static interface for `CoreFoundation`:

* **Loading the Library**: `_cf = ctypes.CDLL(...)` loads `CoreFoundation.framework`.
* **Type Safety**: Defines Python aliases for C types (e.g., `CFStringRef`, `CFNotificationCenterRef`) to ensure correct data handling.
* **Function Prototypes**: Explicitly defines `argtypes` and `restype` for every C function. This prevents segmentation faults caused by passing Python objects where C pointers are required.

### 2. The Callback Mechanism
We must provide a function that the C framework can execute when the event occurs:

1.  **`_notification_callback_c`**: A global Python function that runs when the notification fires. It receives the `app_instance` (our Python object) as context and sets a flag on it.
2.  **`CTYPES_CALLBACK`**: A `ctypes` wrapper that converts the Python function into a C function pointer compatible with `CoreFoundation`.

### 3. Memory Management (Critical Optimization)
This implementation addresses potential memory leaks found in simpler `ctypes` approaches:

* **String Reuse**: The C-string for the notification name (`com.apple...`) is created **once** in `__init__` and stored in `self.cf_notification_name`.
* **Lifecycle**: This single pointer is reused for *Adding* the observer and *Removing* the observer. It is explicitly released (`CFRelease`) only when the app quits.

### 4. Threading & Run Loops
* **Background Thread**: The listener runs on a dedicated background thread (`run_listener`) because `CFRunLoopRun()` blocks execution while waiting for events.
* **Main Thread Safety**: The background thread **never** touches the UI. It acts as a producer, setting a boolean flag (`self.mute_event_received = True`).
* **Polling**: A `@rumps.timer` on the main thread acts as the consumer, checking this flag every 0.1s. If true, it updates the UI. This ensures thread safety and prevents GUI freezes.

## Integration Guide

To add this functionality to your own `rumps` application:

1.  **Copy the Bridge**: Copy the `CFBridge` class and the `_notification_callback_c` function (including the `CTYPES_CALLBACK` line) into your script.

2.  **Update `__init__`**: Initialize the state and the `CFString` in your app's constructor:
    ```python
    def __init__(self):
        super(YourApp, self).__init__("Your App")
        
        # State flags
        self.mute_event_received = False
        self.listener_thread = None
        self.run_loop = None

        # Create the C-String ONCE
        self.cf_notification_name = CFBridge.StringCreateWithCString(
            CFBridge.kCFAllocatorDefault,
            b"com.apple.audioaccessoryd.MuteState",
            CFBridge.kCFStringEncodingUTF8
        )

        self.start_listener()
    ```

3.  **Copy Helper Methods**: Copy `start_listener` and `run_listener` into your class.

4.  **Add the Logic Timer**:
    ```python
    @rumps.timer(0.1)
    def check_for_event(self, _):
        if self.mute_event_received:
            # --- YOUR CUSTOM LOGIC HERE ---
            # e.g., self.toggle_system_mute()
            # ------------------------------
            self.mute_event_received = False
    ```

5.  **Implement Cleanup**: Ensure you copy the `quit_app` logic. It is vital to use `CFBridge.RemoveObserver` passing the **exact same** `self.cf_notification_name` you created in `__init__`, and then release it.
