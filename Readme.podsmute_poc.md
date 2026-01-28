# PodsMute POC: Darwin Notification Listener

This document explains how the `podsmute_poc.py` script works. The goal of this Proof-of-Concept (POC) is to create a Python menu bar application that can listen for the mute button press on AirPods and react to it.

## The Challenge: Listening to System Events

The core difficulty is that there is no direct Python API to listen for the AirPods mute button press. This event is not a standard keyboard shortcut or media key. Instead, it's a private, low-level system notification broadcast by a macOS service (`audioaccessoryd`).

The name of this notification is `com.apple.audioaccessoryd.MuteState`. It's a "Darwin" notification, which is a C-level mechanism for inter-process communication on macOS.

To capture this in Python, we cannot use standard libraries. We must interface directly with macOS's native `CoreFoundation` C framework.

## The Solution: `ctypes` Bridge to CoreFoundation

After discovering that the `pyobjc` library was unreliable for this specific task in the target environment, the final solution uses Python's built-in `ctypes` library. `ctypes` provides a robust, low-level way to call functions in shared libraries (like system frameworks) directly from Python. It acts as a bridge, allowing our Python code to behave like C code.

Here's a breakdown of how the script is architected:

### 1. The `ctypes` Setup

This large block at the beginning of the script is essentially a mini C header file translated into Python. It tells `ctypes` about the C functions and data types we need to use from the `CoreFoundation` framework.

- **Loading the Library**: `_cf = ctypes.CDLL(...)` loads the `CoreFoundation.framework` into our script so we can call its functions.
- **Defining C Types**: Lines like `CFNotificationCenterRef = ctypes.c_void_p` define Python aliases for C pointer types. This makes the code more readable and ensures `ctypes` handles data correctly.
- **Defining Function Prototypes**: Lines like `_cf.CFNotificationCenterAddObserver.argtypes = [...]` and `...restype = ...` define the exact signature of the C functions we want to call. This is crucial for `ctypes` to correctly manage arguments and return values.

### 2. The Callback Mechanism (The Core Logic)

This is the most critical part. We need to provide a Python function that can be successfully called from the C `CoreFoundation` framework.

1.  **`_notification_callback_c`**: This is a simple, global Python function. It's the code that will actually run when a notification is received. It takes several arguments that the C framework provides, but the most important one is `app_instance`. This is the "context" we provide during registration, which allows the callback to know which `rumps` app instance to modify.

2.  **`CFNotificationCallback = ctypes.CFUNCTYPE(...)`**: This line defines the *signature* of a C function pointer in `ctypes` terms. We are telling `ctypes`, "We need to create a callback that returns nothing (`None`) and takes these specific types of arguments (`CFNotificationCenterRef`, `ctypes.py_object`, etc.)."

3.  **`CTYPES_CALLBACK = CFNotificationCallback(...)`**: This is the magic step. It takes our Python function (`_notification_callback_c`) and wraps it, creating a C-compatible function pointer (`CTYPES_CALLBACK`) that we can pass to the `CoreFoundation` framework.

### 3. Threading: Keeping the UI Responsive

- The listener for Darwin notifications must run on a thread with an active "Run Loop". `CFRunLoopRun()` is a blocking call that waits for events.
- If we ran this on the main application thread, our entire `rumps` GUI would freeze.
- Therefore, we create a background `threading.Thread` (`run_listener`) whose sole purpose is to start this run loop and wait for notifications.

### 4. Cross-Thread Communication

- When the `_notification_callback_c` is executed, it's running on the background listener thread. **It is unsafe to directly modify GUI elements (like `self.title`) from a background thread.**
- The safe way to communicate is by using a simple flag.
    1.  The background callback sets `app_instance.mute_event_received = True`.
    2.  A `@rumps.timer` on the main thread (`check_for_event`) periodically checks for this flag.
    3.  If the flag is `True`, the main thread performs the UI update (changing the icon) and resets the flag to `False`.

## How to Integrate This Into Your App

You can copy this functionality into your existing `rumps` application by following these steps:

1.  **Copy the Setup**: Copy the entire `ctypes setup` block and the global `_notification_callback_c` function and `CTYPES_CALLBACK` creation into your script.

2.  **Add `__init__` Logic**: In your `rumps.App` subclass's `__init__` method, add the following attributes and call `start_listener`:
    ```python
    def __init__(self):
        super(YourApp, self).__init__("Your App")
        # ... your other setup ...
        self.mute_event_received = False
        self.listener_thread = None
        self.run_loop = None
        self.start_listener()
    ```

3.  **Copy Helper Methods**: Copy the `start_listener` and `run_listener` methods directly into your `rumps.App` subclass.

4.  **Add the Timer**: Add the `@rumps.timer` method (`check_for_event`) to your class. This is where you will put your desired logic. Instead of changing the title, you can call whatever function you need.
    ```python
    @rumps.timer(0.2) # Or a different interval
    def check_for_airpods_event(self, _):
        if self.mute_event_received:
            print("AirPods mute button was pressed!")
            # --- YOUR LOGIC HERE ---
            # For example: self.toggle_system_mute()
            # -----------------------
            self.mute_event_received = False # Reset the flag
    ```

5.  **Add Cleanup Logic**: It's important to clean up the notification listener when your app quits. Copy the logic from `quit_app` into your own quit method. The key is to call `CFRunLoopStop` to allow the background thread to exit gracefully.

By following these steps, you can add this robust, low-level event listening capability to any `rumps` application.
