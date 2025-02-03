import os
import random
import subprocess
import sys
from tkinter import Tk, Label


"""
Script to automatically change 3-6 desktop wallpapers on Mac using a photos folder.
"""

# Path to your wallpapers folder on the Desktop
wallpapers_folder = os.path.expanduser('~/Desktop/Wallpapers')

# Get a list of all image files in the wallpapers folder
image_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff')
available_wallpapers = []
for root, _, files in os.walk(wallpapers_folder):
    for file in files:
        if file.lower().endswith(image_extensions):
            available_wallpapers.append(os.path.join(root, file))

# Check if wallpapers are found
if not available_wallpapers:
    print(f"No wallpapers found in '{wallpapers_folder}'")
    sys.exit(1)

# Ensure we have enough wallpapers for desktops 1-3 in both runs (6 wallpapers)
if len(available_wallpapers) < 6:
    print(f"Not enough wallpapers ({len(available_wallpapers)}) for 6 wallpapers.")
    print("Please add more wallpapers to your Wallpapers folder.")
    sys.exit(1)

# Shuffle the wallpapers
random.shuffle(available_wallpapers)

# Assign wallpapers to desktops 1-3 for the first run
assigned_wallpapers_first_run = available_wallpapers[:3]

# Assign wallpapers to desktops 1-3 for the second run (without repeats)
assigned_wallpapers_second_run = available_wallpapers[3:6]

def set_wallpapers_on_desktops(desktop_numbers, wallpapers):
    apple_script_lines = ['tell application "System Events"']
    for i, desktop_number in enumerate(desktop_numbers):
        wallpaper = wallpapers[i]
        wallpaper_escaped = wallpaper.replace('"', '\\"')
        set_wallpaper_script = f'set picture of desktop {desktop_number} to "{wallpaper_escaped}"'
        apple_script_lines.append(set_wallpaper_script)
        print(f"Assigned new wallpaper to desktop {desktop_number}: {wallpaper}")
    apple_script_lines.append('end tell')
    apple_script = '\n'.join(apple_script_lines)
    subprocess.run(['osascript', '-e', apple_script])

# Change wallpapers on desktops 1-3 (first run)
desktops_1_to_3 = [1, 2, 3]
set_wallpapers_on_desktops(desktops_1_to_3, assigned_wallpapers_first_run)

# Display a countdown timer during the 10-second pause
def countdown_timer(seconds):
    root = Tk()
    root.title("Countdown Timer")
    root.geometry("300x150")
    root.resizable(False, False)
    label = Label(root, text="", font=("Helvetica", 48))
    label.pack(expand=True)

    def update_label():
        nonlocal seconds
        if seconds >= 0:
            label.config(text=str(seconds))
            seconds -= 1
            root.after(1000, update_label)
        else:
            root.destroy()

    update_label()
    root.mainloop()

# Start the countdown timer
countdown_timer(5)

# Change wallpapers on desktops 1-3 again (second run)
set_wallpapers_on_desktops(desktops_1_to_3, assigned_wallpapers_second_run)

