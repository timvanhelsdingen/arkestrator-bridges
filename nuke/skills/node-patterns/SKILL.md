---
name: node-patterns
description: "Node Patterns patterns and best practices for nuke"
metadata:
  program: nuke
  category: bridge
  title: Node Patterns
  keywords: ["nuke", "nodes", "graph", "channels", "expressions", "tcl"]
  source: bridge-repo
  related-skills: ["compositing", "python-api"]
---

# Nuke Node Graph Patterns

## Common Node Categories

### Input/Output
- **Read** -- Load image sequences, MOVs, EXRs
- **Write** -- Render/export to disk
- **Constant** -- Generate solid color
- **CheckerBoard** -- Generate test pattern
- **ColorBars** -- Generate color bars

### Color
- **Grade** -- Primary color correction (lift/gain/multiply/offset/gamma)
- **ColorCorrect** -- Shadows/midtones/highlights separation
- **HueCorrect** -- Hue-based color manipulation
- **Saturation** -- Simple saturation control
- **Clamp** -- Clamp values to range
- **Colorspace** -- Convert between color spaces
- **OCIOColorSpace** -- OCIO-based color management

### Compositing
- **Merge2** -- Composite two inputs (over, plus, multiply, screen, etc.)
- **Premult** / **Unpremult** -- Alpha premultiplication
- **Keymix** -- Mix between A and B using mask
- **Switch** -- Switch between inputs by index
- **Dissolve** -- Cross-dissolve between inputs

### Transform
- **Transform** -- 2D transform (translate, rotate, scale)
- **Reformat** -- Change resolution/format
- **Crop** -- Crop to region
- **Mirror** -- Flip/flop
- **CornerPin2D** -- 4-corner perspective transform
- **SplineWarp** -- Spline-based warping

### Keying
- **Keylight** -- Foundry's screen-based keyer
- **Primatte** -- Advanced chroma keyer
- **IBKGizmo** -- Image-based keyer
- **HueKeyer** -- Hue-range keyer
- **Difference** -- Difference matte

### Filter
- **Blur** -- Gaussian blur
- **Defocus** -- Lens defocus/bokeh
- **Sharpen** -- Sharpen filter
- **EdgeDetect** -- Find edges
- **Erode** -- Grow/shrink mattes
- **Dilate** -- Dilate/erode with filtering
- **Median** -- Median filter
- **VectorBlur** -- Motion-vector-based blur
- **ZDefocus** -- Depth-based defocus

### 3D/Deep
- **ScanlineRender** -- Built-in 3D renderer
- **Camera2** -- 3D camera
- **Scene** -- 3D scene container
- **ReadGeo2** -- Import 3D geometry
- **Card2** -- 3D card/plane
- **DeepRead** / **DeepWrite** -- Deep image I/O
- **DeepMerge** -- Merge deep images

### Channel
- **Shuffle2** -- Rearrange channels between layers
- **Copy** -- Copy channels from one stream to another
- **ChannelMerge** -- Combine channels with operations
- **Remove** -- Remove channels/layers

### Draw/Paint
- **Roto** -- Bezier/B-spline shapes for masking
- **RotoPaint** -- Paint strokes and clone operations
- **Noise** -- Procedural noise generation

### Tracking
- **Tracker4** -- Point tracker (translate/rotate/scale/perspective)
- **CameraTracker** -- 3D camera solve from 2D tracks
- **Stabilize2D** -- Stabilize footage from tracking data
- **MatchMove** -- Apply tracking data to elements

### Utility
- **Dot** -- Pass-through for graph organization
- **NoOp** -- No operation (useful as control node)
- **BackdropNode** -- Visual organization backdrop
- **Group** -- Group nodes together
- **StickyNote** -- Annotation text in graph
- **Viewer** -- Preview node output
- **FrameHold** -- Hold a specific frame
- **TimeOffset** -- Offset timing

## Graph Organization Best Practices
- Flow top-to-bottom (Read at top, Write at bottom)
- Use Dot nodes to route connections clearly
- Use Backdrop nodes with labels for sections
- Name nodes descriptively (e.g., `fg_grade`, `bg_despill`)
- Keep the main comp backbone as a single vertical stream
- Branch off for secondary operations, merge back in

## Expression Patterns
- `[value root.first_frame]` -- Project first frame
- `[value root.last_frame]` -- Project last frame
- `[value root.name]` -- Script file path
- `[value this.input0.width]` -- Input width
- `[frame]` -- Current frame number
- `clamp(value, min, max)` -- Clamp expression
- `curve` -- Animation curve
- `(sin(frame/24.0) + 1) / 2` -- Oscillating value
