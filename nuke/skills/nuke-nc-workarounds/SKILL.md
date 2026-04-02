---
name: nuke-nc-workarounds
description: "Critical workarounds for Nuke NC (Non-Commercial) API quirks — node enumeration, stale references, and reliable patterns"
metadata:
  program: nuke
  category: bridge
  title: Nuke NC Workarounds
  keywords: ["nuke", "nuke-nc", "non-commercial", "allNodes", "toNode", "workarounds", "node-enumeration", "stale-references"]
  source: bridge-repo
  priority: 90
  auto-fetch: true
  related-skills: ["python-api", "node-patterns", "verification"]
---

# Nuke NC (Non-Commercial) Bridge Workarounds

## CRITICAL: Read This First

Nuke NC has known API quirks that cause standard Python patterns to fail intermittently.
The bridge includes built-in workarounds, but agents MUST use the reliable patterns below.

## Known Issues

### 1. `nuke.allNodes()` Returns Inconsistent Results
**Symptom:** Unfiltered `allNodes()` returns different node counts on each call (sometimes 1, sometimes 11).
**Root Cause:** Nuke NC's internal graph isn't always fully synchronized when Python executes.
**Fix:** Always use class-filtered queries or the bridge helper `_ark_all_nodes()`.

### 2. `nuke.toNode("name")` Returns None
**Symptom:** Node exists in the graph but `toNode()` can't find it.
**Root Cause:** Graph state not synced, or node name changed since last reference.
**Fix:** Use `_ark_find_node("name")` which syncs the graph first and falls back to allNodes() search.

### 3. `nuke.createNode()` Returns None
**Symptom:** Node IS created in the graph but the Python return value is None.
**Root Cause:** Thread timing issue in NC mode.
**Fix:** Create the node, then immediately find it by name:
```python
nuke.createNode("Grade")
grade = _ark_find_node("Grade1")  # bridge helper
```

### 4. `node.input(i)` Returns None
**Symptom:** Connections exist visually but `input()` returns None.
**Root Cause:** Stale node reference or graph not synced.
**Fix:** Use `node.dependent()` (most reliable) or re-acquire the reference:
```python
node = _ark_find_node("Merge1")
deps = node.dependent()  # most reliable for discovering connections
```

### 5. `.nknc` Files Are Encrypted
**Symptom:** Cannot read script files as text.
**Fix:** MUST use live session API. Never try to read .nknc files directly.

## Reliable Patterns

### Node Enumeration (DO THIS)
```python
# GOOD: Class-filtered queries are reliable
reads = nuke.allNodes("Read")
writes = nuke.allNodes("Write")
merges = nuke.allNodes("Merge2")

# GOOD: Bridge helper with multi-pass enumeration
all_nodes = _ark_all_nodes()

# GOOD: Discover graph structure via dependencies
node = _ark_find_node("Write1")
upstream = node.dependencies()  # all nodes feeding into this one

# BAD: Unfiltered allNodes() is unreliable in NC
nodes = nuke.allNodes()  # DO NOT rely on this count
```

### Node Creation (DO THIS)
```python
# GOOD: Create then find by expected name
nuke.createNode("Grade")
grade = _ark_find_node("Grade1")
if grade:
    grade["multiply"].setValue(1.5)

# GOOD: Use TCL for creation + naming in one shot
nuke.tcl('Grade { name my_grade multiply 1.5 }')
grade = _ark_find_node("my_grade")

# GOOD: Create with explicit name
node = nuke.createNode("Grade", inpanel=False)
if node:
    node.setName("my_grade")
else:
    node = _ark_find_node("Grade1")
```

### Reading Knob Values (DO THIS)
```python
# GOOD: TCL value command is always reliable for known nodes
result = nuke.tcl('value Grade1.multiply')

# GOOD: Re-acquire reference before reading knobs
node = _ark_find_node("Grade1")
if node:
    val = node["multiply"].value()

# BAD: Using a stale reference from a previous command
# (this works in the bridge because session is persistent,
#  but re-acquire if you get AttributeError)
```

### Graph Traversal (DO THIS)
```python
# GOOD: dependent() is the most reliable traversal method
node = _ark_find_node("Read1")
downstream = node.dependent()
for d in downstream:
    print(f"  -> {d.name()} ({d.Class()})")

# GOOD: dependencies() for upstream traversal
node = _ark_find_node("Write1")
upstream = node.dependencies()

# GOOD: Walk the full graph from Write nodes
for write in nuke.allNodes("Write"):
    print(f"\nWrite: {write.name()} -> {write['file'].value()}")
    _walk_upstream(write, depth=0)

def _walk_upstream(node, depth=0):
    for i in range(node.inputs()):
        inp = node.input(i)
        if inp:
            print(f"{'  ' * (depth+1)}input[{i}]: {inp.name()} ({inp.Class()})")
            _walk_upstream(inp, depth+1)
        else:
            # Fallback: use dependencies if input() fails
            for dep in node.dependencies():
                print(f"{'  ' * (depth+1)}dep: {dep.name()} ({dep.Class()})")
```

### Verification Pattern
```python
# Always verify after creation/modification
nuke.createNode("Blur")
_ark_sync_graph()  # force sync

# Verify by class query (reliable)
blurs = nuke.allNodes("Blur")
found = any(b.name() == "Blur1" for b in blurs)
print(f"PASS: Blur1 created" if found else "FAIL: Blur1 not found")

# Verify connections via dependent()
source = _ark_find_node("Read1")
blur = _ark_find_node("Blur1")
if blur and source:
    is_connected = source in blur.dependencies()
    print(f"PASS: connected" if is_connected else "FAIL: not connected")
```

## Bridge Helper Functions

The bridge injects these helpers into the Python execution context:

| Helper | Description |
|--------|-------------|
| `_ark_sync_graph()` | Force node graph synchronization before enumeration |
| `_ark_all_nodes(class_filter="")` | Reliable allNodes with multi-pass enumeration |
| `_ark_find_node("name")` | Reliable toNode with graph sync and fallback search |

## Anti-Patterns (NEVER DO)

1. **Never** rely on `len(nuke.allNodes())` for node counting
2. **Never** cache node references across separate execute_command calls without re-acquiring
3. **Never** read `.nknc` files from disk -- use the live API only
4. **Never** assume `createNode()` return value is valid -- always verify
5. **Never** use `node.input(i)` as the sole method to discover connections -- use `dependent()`/`dependencies()` as fallback
