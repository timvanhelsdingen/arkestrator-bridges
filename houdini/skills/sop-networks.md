---
title: SOP Networks
category: bridge
---
# Houdini SOP Networks

## Creating Geometry Nodes
- Create geo container: `hou.node("/obj").createNode("geo", "my_geo")`
- Inside geo, create SOPs: `geo.createNode("sphere")`, `geo.createNode("box")`
- Connect nodes: `node2.setInput(0, node1)`
- Set display: `node.setDisplayFlag(True)` and `node.setRenderFlag(True)`

## Common SOPs
- Primitives: sphere, box, tube, grid, circle, torus
- Transform: xform (translate/rotate/scale geometry)
- Copy: copytopoints (instance geometry onto points)
- Merge: merge (combine multiple inputs)
- Boolean: boolean (union/intersect/subtract)
- Scatter: scatter (random points on surface)

## Parameters
- Set: `node.parm("tx").set(1.5)` or `node.parmTuple("t").set((1, 2, 3))`
- Expression: `node.parm("tx").setExpression("$F * 0.1")`

## VEX in Wrangle
- Point wrangle: `geo.createNode("attribwrangle")`
- Set snippet: `node.parm("snippet").set("@P.y = sin(@P.x);")`
- Runs per point by default (Run Over = Points)
