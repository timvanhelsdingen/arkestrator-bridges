-- Arkestrator auto-start script
-- Called by Arkestrator.fu on composition open/create.
-- Launches the Python bridge in headless (background) mode.

local bridgePath = app:MapPath("Config:/Arkestrator/arkestrator_bridge.py")
if not bmd.fileexists(bridgePath) then
    print("[Arkestrator] Bridge not found: " .. bridgePath)
    return
end

-- Check if bridge is already running by looking for the global flag
if ARKESTRATOR_RUNNING then
    print("[Arkestrator] Bridge already running, skipping auto-start")
    return
end

-- Set global flag before launching
ARKESTRATOR_RUNNING = true

-- Run the bridge in headless mode via environment variable
-- The Python bridge checks this to skip the UI panel
comp:Execute([[
import os
os.environ["ARKESTRATOR_HEADLESS"] = "1"
os.environ["ARKESTRATOR_AUTOSTART"] = "1"
]])

comp:RunScript(bridgePath)
