import rumps
import subprocess
from AppKit import NSStatusBar, NSVariableStatusItemLength, NSImage

# --- CONFIGURATION ---
TEAMS_PROCESS_NAME = "Microsoft Teams"

# ICONS
ICON_MUTED = "🔴"
ICON_LIVE = "🟢"
ICON_MENU = "⚙️"  # The icon for the menu button


class SplitTeamsController(rumps.App):
    def __init__(self):
        # 1. SETUP THE MENU APP (The Gear Icon)
        super(SplitTeamsController, self).__init__("TeamsMenu", icon=None, title=ICON_MENU)

        self.is_muted = self.check_system_mute_status()

        # Menu Items
        self.menu = [
            rumps.MenuItem("Auflegen (Hang Up)", callback=self.hang_up),
            rumps.MenuItem("Teams zeigen (Focus)", callback=self.show_window),
            None,
            "Beenden"
        ]

        # 2. SETUP THE SECOND ICON (The Mic Toggle)
        # We have to use native macOS calls (AppKit) to add a second item to the bar
        self.statusbar = NSStatusBar.systemStatusBar()
        self.mic_item = self.statusbar.statusItemWithLength_(NSVariableStatusItemLength)
        self.mic_item.button().setTitle_(ICON_MUTED if self.is_muted else ICON_LIVE)

        # Assign the click action to the 'quick_toggle' function
        self.mic_item.button().setTarget_(self)
        self.mic_item.button().setAction_("quickToggle:")

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

    # --- SYSTEM AUDIO CONTROL ---
    def mute_system(self):
        subprocess.run(["osascript", "-e", "set volume input volume 0"])

    def unmute_system(self):
        subprocess.run(["osascript", "-e", "set volume input volume 100"])

    def check_system_mute_status(self):
        script = "input volume of (get volume settings)"
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True).stdout.strip()
        try:
            return int(result) == 0
        except ValueError:
            return False


if __name__ == "__main__":
    SplitTeamsController().run()
