-- Arkestrator auto-start script
-- Called by Arkestrator.fu on composition open/create.
-- Launches the Python bridge in headless (background) mode.
--
-- The bridge stays alive because main() runs Fusion's UIDispatcher.RunLoop()
-- which keeps the fuscript.exe process alive for the entire session.

local bridgePath = app:MapPath("Config:/Arkestrator/arkestrator_bridge.py")
if not bmd.fileexists(bridgePath) then
    print("[Arkestrator] Bridge not found: " .. bridgePath)
    return
end

-- Guard: prevent multiple launches within the same Fusion session
if ARKESTRATOR_RUNNING then
    print("[Arkestrator] Bridge already running, skipping auto-start")
    return
end

ARKESTRATOR_RUNNING = true

-- Set headless mode so the bridge uses the hidden event loop (not the UI panel)
comp:Execute([[
import os
os.environ["ARKESTRATOR_HEADLESS"] = "1"
]])

comp:RunScript(bridgePath)
