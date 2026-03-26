#!/usr/bin/env node
/**
 * Updates the version across ALL bridge plugins in one shot.
 *
 * Usage:
 *   node scripts/bump-version.mjs 0.1.80
 *
 * Files updated:
 *   - blender/arkestrator_bridge/blender_manifest.toml
 *   - godot/addons/arkestrator_bridge/plugin.cfg
 *   - unreal/ArkestratorBridge/ArkestratorBridge.uplugin
 *   - blackmagic-fusion/Arkestrator/config.py
 */
import { readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const root = resolve(__dirname, "..");

const version = process.argv[2];

if (!version || !/^\d+\.\d+\.\d+(-[\w.]+)?$/.test(version)) {
  console.error("Usage: node scripts/bump-version.mjs <version>");
  console.error("  e.g. node scripts/bump-version.mjs 0.1.80");
  process.exit(1);
}

console.log(`Bumping all bridge plugins to ${version}\n`);

// --- Blender manifest (TOML) ---
const blenderPath = join(root, "blender/arkestrator_bridge/blender_manifest.toml");
try {
  let content = readFileSync(blenderPath, "utf8");
  content = content.replace(/^(version\s*=\s*)"[^"]*"/m, `$1"${version}"`);
  writeFileSync(blenderPath, content);
  console.log(`  ✓ blender blender_manifest.toml → ${version}`);
} catch (err) {
  console.warn(`  ⚠ blender manifest skipped (${err.code ?? err.message})`);
}

// --- Godot plugin.cfg ---
const godotPath = join(root, "godot/addons/arkestrator_bridge/plugin.cfg");
try {
  let content = readFileSync(godotPath, "utf8");
  content = content.replace(/^(version\s*=\s*)"[^"]*"/m, `$1"${version}"`);
  writeFileSync(godotPath, content);
  console.log(`  ✓ godot plugin.cfg → ${version}`);
} catch (err) {
  console.warn(`  ⚠ godot plugin.cfg skipped (${err.code ?? err.message})`);
}

// --- Unreal .uplugin (JSON) ---
const unrealPath = join(root, "unreal/ArkestratorBridge/ArkestratorBridge.uplugin");
try {
  const uplugin = JSON.parse(readFileSync(unrealPath, "utf8"));
  uplugin.VersionName = version;
  writeFileSync(unrealPath, JSON.stringify(uplugin, null, "\t") + "\n");
  console.log(`  ✓ unreal ArkestratorBridge.uplugin → ${version}`);
} catch (err) {
  console.warn(`  ⚠ unreal .uplugin skipped (${err.code ?? err.message})`);
}

// --- Fusion config.py ---
const fusionPath = join(root, "blackmagic-fusion/Arkestrator/config.py");
try {
  let content = readFileSync(fusionPath, "utf8");
  content = content.replace(
    /^(BRIDGE_VERSION\s*=\s*)"[^"]*"/m,
    `$1"${version}"`,
  );
  writeFileSync(fusionPath, content);
  console.log(`  ✓ fusion config.py → ${version}`);
} catch (err) {
  console.warn(`  ⚠ fusion config.py skipped (${err.code ?? err.message})`);
}

console.log(`\n✅ All bridge plugins updated to ${version}`);
