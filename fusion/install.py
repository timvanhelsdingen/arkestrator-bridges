"""
Arkestrator Fusion Bridge — Installer

Run this script to install the bridge into Fusion's Scripts directory.
Works for both standalone Fusion and DaVinci Resolve.

Usage:
    python install.py                    # Auto-detect Fusion installation
    python install.py --resolve          # Install for DaVinci Resolve
    python install.py --path /custom     # Install to a custom path
"""

import argparse
import os
import platform
import shutil
import sys


def get_fusion_scripts_dirs():
    """Return candidate Fusion script directories."""
    system = platform.system()
    home = os.path.expanduser("~")
    dirs = []

    if system == "Windows":
        appdata = os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
        # Standalone Fusion
        dirs.append(os.path.join(appdata, "Blackmagic Design", "Fusion", "Scripts", "Comp"))
        # DaVinci Resolve
        dirs.append(os.path.join(appdata, "Blackmagic Design", "DaVinci Resolve", "Fusion", "Scripts", "Comp"))
    elif system == "Darwin":
        dirs.append(os.path.join(home, "Library", "Application Support",
                                 "Blackmagic Design", "Fusion", "Scripts", "Comp"))
        dirs.append(os.path.join(home, "Library", "Application Support",
                                 "Blackmagic Design", "DaVinci Resolve", "Fusion", "Scripts", "Comp"))
    else:  # Linux
        dirs.append(os.path.join(home, ".fusion", "BlackmagicDesign", "Fusion", "Scripts", "Comp"))
        dirs.append(os.path.join(home, ".local", "share", "DaVinciResolve", "Fusion", "Scripts", "Comp"))

    return dirs


def install(target_dir):
    """Install the bridge to the target directory."""
    bridge_dir = os.path.dirname(os.path.abspath(__file__))
    dest = os.path.join(target_dir, "Arkestrator")

    # Ensure target exists
    os.makedirs(target_dir, exist_ok=True)

    # Copy the bridge package
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(bridge_dir, dest, ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", ".git", "install.py",
    ))

    # Create a launcher script in the parent Scripts/Comp directory
    launcher_path = os.path.join(target_dir, "Arkestrator_Connect.py")
    launcher_content = f'''"""Arkestrator Bridge — launch from Fusion's Script menu."""
import sys, os
bridge_dir = os.path.dirname(os.path.abspath(__file__))
parent = os.path.dirname(bridge_dir) if "Arkestrator" not in bridge_dir else os.path.dirname(bridge_dir)
# Add both the Scripts/Comp dir and the bridge package parent to path
for p in [bridge_dir, parent]:
    if p not in sys.path:
        sys.path.insert(0, p)
# The bridge package lives in Scripts/Comp/Arkestrator/
ark_dir = os.path.join(bridge_dir, "Arkestrator")
ark_parent = os.path.dirname(ark_dir)
if ark_parent not in sys.path:
    sys.path.insert(0, ark_parent)

# Rename package for import (it's in "Arkestrator/" but we import as "fusion")
import importlib
spec = importlib.util.spec_from_file_location(
    "fusion", os.path.join(ark_dir, "__init__.py"),
    submodule_search_locations=[ark_dir]
)
fusion_pkg = importlib.util.module_from_spec(spec)
sys.modules["fusion"] = fusion_pkg
spec.loader.exec_module(fusion_pkg)

# Now load and run submodules
for mod_name in ["config", "ws_client", "context_provider", "command_executor", "file_applier"]:
    mod_spec = importlib.util.spec_from_file_location(
        f"fusion.{{mod_name}}", os.path.join(ark_dir, f"{{mod_name}}.py")
    )
    mod = importlib.util.module_from_spec(mod_spec)
    sys.modules[f"fusion.{{mod_name}}"] = mod
    mod_spec.loader.exec_module(mod)

# Import and run the bridge
bridge_spec = importlib.util.spec_from_file_location(
    "fusion.arkestrator_bridge", os.path.join(ark_dir, "arkestrator_bridge.py")
)
bridge_mod = importlib.util.module_from_spec(bridge_spec)
bridge_spec.loader.exec_module(bridge_mod)
bridge_mod.main()
'''
    with open(launcher_path, "w", encoding="utf-8") as f:
        f.write(launcher_content)

    print(f"Installed Arkestrator bridge to: {dest}")
    print(f"Launcher created at: {launcher_path}")
    print()
    print("In Fusion: Script > Arkestrator_Connect")
    return True


def main():
    parser = argparse.ArgumentParser(description="Install Arkestrator Fusion Bridge")
    parser.add_argument("--path", help="Custom installation path")
    parser.add_argument("--resolve", action="store_true", help="Install for DaVinci Resolve")
    args = parser.parse_args()

    if args.path:
        install(args.path)
        return

    candidates = get_fusion_scripts_dirs()
    if args.resolve:
        candidates = [d for d in candidates if "Resolve" in d or "DaVinci" in d]

    installed = False
    for d in candidates:
        parent = os.path.dirname(d)
        if os.path.isdir(parent):
            install(d)
            installed = True

    if not installed:
        print("Could not find Fusion installation directory.")
        print("Use --path to specify manually:")
        print(f"  python install.py --path /path/to/Fusion/Scripts/Comp")
        sys.exit(1)


if __name__ == "__main__":
    main()
