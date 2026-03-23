"""
Arkestrator Fusion Bridge — Installer

Installs the bridge into Fusion's Config directory so it auto-starts
when a composition is opened or created.

Layout after install:
    Config/Arkestrator.fu              <- menu + event registration
    Config/Arkestrator/                <- bridge package + startup script
        arkestrator_startup.lua
        arkestrator_bridge.py
        arkestrator_connect.py
        arkestrator_disconnect.py
        arkestrator_panel.py
        ws_client.py
        config.py
        context_provider.py
        command_executor.py
        file_applier.py
        __init__.py
        skills/

Works for both standalone Fusion and DaVinci Resolve.

Usage:
    python install.py                    # Auto-detect Fusion installation
    python install.py --resolve          # Install for DaVinci Resolve
    python install.py --path /custom     # Install to a custom Config path
"""

import argparse
import os
import platform
import shutil
import sys


def get_fusion_config_dirs():
    """Return candidate Fusion Config directories."""
    system = platform.system()
    home = os.path.expanduser("~")
    dirs = []

    if system == "Windows":
        appdata = os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
        # Standalone Fusion
        dirs.append(os.path.join(appdata, "Blackmagic Design", "Fusion", "Config"))
        # DaVinci Resolve
        dirs.append(os.path.join(appdata, "Blackmagic Design", "DaVinci Resolve", "Fusion", "Config"))
    elif system == "Darwin":
        dirs.append(os.path.join(home, "Library", "Application Support",
                                 "Blackmagic Design", "Fusion", "Config"))
        dirs.append(os.path.join(home, "Library", "Application Support",
                                 "Blackmagic Design", "DaVinci Resolve", "Fusion", "Config"))
    else:  # Linux
        dirs.append(os.path.join(home, ".fusion", "BlackmagicDesign", "Fusion", "Config"))
        dirs.append(os.path.join(home, ".local", "share", "DaVinciResolve", "Fusion", "Config"))

    return dirs


def clean_legacy_install(config_dir):
    """Remove old Scripts/Comp installations if they exist."""
    # The old installer put files in Scripts/Comp/Arkestrator/ and
    # Scripts/Comp/Arkestrator_Connect.py. Clean those up.
    fusion_root = os.path.dirname(config_dir)  # e.g. .../Fusion/
    scripts_comp = os.path.join(fusion_root, "Scripts", "Comp")

    legacy_dir = os.path.join(scripts_comp, "Arkestrator")
    legacy_launcher = os.path.join(scripts_comp, "Arkestrator_Connect.py")

    removed = []
    if os.path.isdir(legacy_dir):
        shutil.rmtree(legacy_dir)
        removed.append(legacy_dir)
    if os.path.isfile(legacy_launcher):
        os.remove(legacy_launcher)
        removed.append(legacy_launcher)

    if removed:
        print(f"  Cleaned legacy install:")
        for r in removed:
            print(f"    removed: {r}")


def install(config_dir):
    """Install the bridge to the Config directory."""
    bridge_src = os.path.dirname(os.path.abspath(__file__))

    # Ensure Config/ exists
    os.makedirs(config_dir, exist_ok=True)

    # 1. Copy Arkestrator.fu -> Config/Arkestrator.fu
    fu_src = os.path.join(bridge_src, "Arkestrator.fu")
    fu_dst = os.path.join(config_dir, "Arkestrator.fu")
    if os.path.isfile(fu_src):
        shutil.copy2(fu_src, fu_dst)
    else:
        print(f"  WARNING: Arkestrator.fu not found in {bridge_src}")

    # 2. Copy bridge package -> Config/Arkestrator/
    dest = os.path.join(config_dir, "Arkestrator")
    if os.path.exists(dest):
        shutil.rmtree(dest)

    shutil.copytree(bridge_src, dest, ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", ".git", "install.py", "Arkestrator.fu",
        "coordinator.md",
    ))

    # 3. Copy the Lua startup script into Config/Arkestrator/
    lua_src = os.path.join(bridge_src, "arkestrator_startup.lua")
    lua_dst = os.path.join(dest, "arkestrator_startup.lua")
    if os.path.isfile(lua_src):
        shutil.copy2(lua_src, lua_dst)

    # 4. Clean up old Scripts/Comp install
    clean_legacy_install(config_dir)

    print(f"Installed Arkestrator bridge to: {dest}")
    print(f"Config file: {fu_dst}")
    print()
    print("The bridge will auto-connect when you open or create a composition.")
    print("Use the Arkestrator menu (before Help) for manual Connect/Disconnect/Panel.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Install Arkestrator Fusion Bridge")
    parser.add_argument("--path", help="Custom Config directory path")
    parser.add_argument("--resolve", action="store_true", help="Install for DaVinci Resolve")
    args = parser.parse_args()

    if args.path:
        install(args.path)
        return

    candidates = get_fusion_config_dirs()
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
        print(f"  python install.py --path /path/to/Fusion/Config")
        sys.exit(1)


if __name__ == "__main__":
    main()
