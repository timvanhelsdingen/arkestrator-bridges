"""
Arkestrator — Add to Context popup.

Triggered by hotkey (Ctrl+Shift+A) or menu. Shows a popup with options
to add selected tools, active tool, or full comp to context.

Since this runs in a separate fuscript.exe process from the bridge,
it communicates via a temp command file that the bridge's headless
event loop picks up.
"""

import json
import os
import tempfile

# IPC command file path — must match _run_headless() in arkestrator_bridge.py
_CMD_PATH = os.path.join(tempfile.gettempdir(), "arkestrator_fusion_cmd.json")


def _send_command(action):
    """Write an IPC command for the bridge process to pick up."""
    try:
        with open(_CMD_PATH, "w") as f:
            json.dump({"action": action}, f)
    except Exception as exc:
        print(f"[Arkestrator] Failed to write command: {exc}")


# Get Fusion app and comp from globals (available in RunScript context)
_fusion_app = None
for _g in ("fusion", "fu", "app"):
    _obj = globals().get(_g)
    if _obj is not None and hasattr(_obj, "UIManager"):
        _fusion_app = _obj
        break

if _fusion_app is None:
    print("[Arkestrator] ERROR: No Fusion app found")
else:
    _comp = globals().get("comp")
    if _comp is None:
        try:
            _comp = _fusion_app.CurrentComp
        except Exception:
            pass

    # Check what's available
    selected = _comp.GetToolList(True) if _comp else {}
    selected = selected or {}
    active = None
    try:
        active = _comp.ActiveTool if _comp else None
    except Exception:
        pass

    num_selected = len(selected)

    # Build popup menu via UI Manager
    ui = _fusion_app.UIManager
    disp = bmd.UIDispatcher(ui)  # noqa: F821 — bmd is a Fusion global

    _win_id = "ArkAddContext"

    win = disp.AddWindow(
        {
            "ID": _win_id,
            "WindowTitle": "Arkestrator",
            "Geometry": [300, 200, 260, 200],
            "WindowFlags": {
                "Window": True,
                "WindowStaysOnTopHint": True,
            },
        },
        ui.VGroup(
            {"Spacing": 4, "Weight": 0},
            [
                ui.Label(
                    {
                        "Text": "Add to Arkestrator Context",
                        "Alignment": {"AlignHCenter": True},
                        "StyleSheet": "font-weight: bold; font-size: 13px; padding: 4px;",
                    }
                ),
                ui.Button(
                    {
                        "ID": "AddSelected",
                        "Text": f"Selected Tools ({num_selected})",
                        "Enabled": num_selected > 0,
                        "StyleSheet": "padding: 6px;",
                    }
                ),
                ui.Button(
                    {
                        "ID": "AddActive",
                        "Text": f"Active Tool ({active.Name if active else 'none'})",
                        "Enabled": active is not None,
                        "StyleSheet": "padding: 6px;",
                    }
                ),
                ui.Button(
                    {
                        "ID": "AddComp",
                        "Text": "Full Composition",
                        "StyleSheet": "padding: 6px;",
                    }
                ),
            ],
        ),
    )

    def on_add_selected(ev):
        _send_command("add_selected")
        print(f"[Arkestrator] Sent: add {num_selected} selected tool(s)")
        disp.ExitLoop()

    def on_add_active(ev):
        _send_command("add_active")
        print(f"[Arkestrator] Sent: add active tool")
        disp.ExitLoop()

    def on_add_comp(ev):
        _send_command("add_comp")
        print("[Arkestrator] Sent: add full composition")
        disp.ExitLoop()

    def on_close(ev):
        disp.ExitLoop()

    win.On[_win_id].Close = on_close
    win.On.AddSelected.Clicked = on_add_selected
    win.On.AddActive.Clicked = on_add_active
    win.On.AddComp.Clicked = on_add_comp

    win.Show()
    disp.RunLoop()
    win.Hide()
