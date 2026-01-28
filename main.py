import rumps
import subprocess

# --- CONFIGURATION ---
TEAMS_PROCESS_NAME = "Microsoft Teams"

# ICONS
ICON_MUTED = "🔴"  # System Mic is 0%
ICON_LIVE = "🟢"  # System Mic is ON


class SystemMuteController(rumps.App):
    def __init__(self):
        super(SystemMuteController, self).__init__("MicCtrl")

        # 1. Check current system volume on startup
        self.is_muted = self.check_system_mute_status()
        self.update_icon()

        # 2. Define the Menu clearly
        self.menu = [
            rumps.MenuItem("Mute umschalten (Toggle)", callback=self.toggle_mute),
            None,  # Separator
            rumps.MenuItem("Auflegen (Hang Up)", callback=self.hang_up),
            rumps.MenuItem("Teams zeigen (Focus)", callback=self.show_window),
            None,
            "Beenden"
        ]

    # --- ACTIONS ---

    def toggle_mute(self, _):
        if self.is_muted:
            self.unmute_system()
        else:
            self.mute_system()

        # Re-check status to be sure
        self.is_muted = self.check_system_mute_status()
        self.update_icon()

    def hang_up(self, _):
        # Sends Cmd+Shift+H to Teams
        script = f'''
        tell application "{TEAMS_PROCESS_NAME}" to activate
        tell application "System Events" to keystroke "h" using {{command down, shift down}}
        '''
        subprocess.run(["osascript", "-e", script])

        # Optional: Reset mic to ON after hanging up?
        # self.unmute_system()
        self.is_muted = self.check_system_mute_status()
        self.update_icon()

    def show_window(self, _):
        script = f'tell application "{TEAMS_PROCESS_NAME}" to activate'
        subprocess.run(["osascript", "-e", script])

    # --- SYSTEM AUDIO CONTROL ---

    def mute_system(self):
        subprocess.run(["osascript", "-e", "set volume input volume 0"])

    def unmute_system(self):
        # Sets input volume to 100. Change to 75 if 100 is too loud.
        subprocess.run(["osascript", "-e", "set volume input volume 100"])

    def check_system_mute_status(self):
        # Returns True if input volume is 0
        script = "input volume of (get volume settings)"
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True).stdout.strip()
        try:
            return int(result) == 0
        except ValueError:
            return False

    def update_icon(self):
        if self.is_muted:
            self.title = ICON_MUTED
            # Optional: Update the menu text to show current state
            # self.menu["Mute umschalten (Toggle)"].title = "Unmute (Mikrofon an)"
        else:
            self.title = ICON_LIVE
            # self.menu["Mute umschalten (Toggle)"].title = "Mute (Stummschalten)"


if __name__ == "__main__":
    SystemMuteController().run()