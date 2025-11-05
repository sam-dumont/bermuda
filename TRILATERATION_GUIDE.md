# Bermuda Trilateration Fork - Setup Guide

This fork adds **real triangulation/trilateration** capabilities to the Bermuda BLE integration, allowing accurate position tracking using multiple Bluetooth scanners.

## What's New?

### Real 3D Position Calculation
- Uses signal strength from **multiple scanners simultaneously**
- Calculates actual X, Y, Z coordinates in meters
- Works with as few as **3 scanners** (ideal for multi-floor homes)
- Much more accurate than "closest scanner only" approach

### Interactive Room Boundary Learning
- Walk around your home to teach the system room boundaries
- Automatic polygon generation from position samples
- No manual coordinate entry required!

### Position Sensors
- X, Y, Z coordinates (disabled by default)
- Trilateration confidence score (0-1)
- Scanner count used in calculation
- Floor plan export for visualization

---

## Quick Start with 3 Scanners

Your setup with 3 ESPHome devices on 3 floors is **perfect** for trilateration!

### Step 1: Set Scanner Positions

Use the `bermuda_tri.set_scanner_position` service to define where each scanner is located.

**Example for 3-floor home:**

```yaml
# Floor 1 Scanner (reference point: 0, 0, 0)
service: bermuda_tri.set_scanner_position
data:
  scanner_address: "AA:BB:CC:DD:EE:01"
  x: 0.0
  y: 0.0
  z: 0.0  # Ground floor

# Floor 2 Scanner (assume ~3m ceiling height)
service: bermuda_tri.set_scanner_position
data:
  scanner_address: "AA:BB:CC:DD:EE:02"
  x: 0.0
  y: 0.0
  z: 3.0  # 3 meters up

# Floor 3 Scanner
service: bermuda_tri.set_scanner_position
data:
  scanner_address: "AA:BB:CC:DD:EE:03"
  x: 0.0
  y: 0.0
  z: 6.0  # 6 meters up (2 floors)
```

**Tip:** You can use any reference point as (0, 0, 0). Measurements are relative!

### Step 2: Enable Trilateration

In the integration configuration:
1. Go to **Settings** → **Devices & Services** → **Bermuda Triangulation Fork**
2. Click **CONFIGURE**
3. Enable **Trilateration Mode** (when configuration UI is added)

*Or manually edit `.storage/core.config_entries` and set `trilateration_enabled: true` in your Bermuda entry*

### Step 3: Enable Position Sensors

For each tracked device:
1. Go to the device page
2. Scroll to disabled sensors
3. Enable:
   - **Position X**
   - **Position Y**
   - **Position Z**
   - **Trilateration Confidence**
   - **Scanner Count**

### Step 4: Learn Room Boundaries (Interactive!)

Walk around your home with your tracked device (phone) and mark positions:

```yaml
# Stand in the living room and run:
service: bermuda_tri.mark_position
data:
  device_address: "YOUR:PHONE:MAC:ADDRESS"
  area_id: living_room  # Select from dropdown!

# Walk around the living room, mark 3-5 more positions
# Then move to kitchen and repeat...
```

**Collect 5-10 samples per room** for best results.

### Step 5: Generate Room Boundaries

After collecting samples:

```yaml
service: bermuda_tri.calculate_room_boundaries
data:
  method: convex_hull  # or "bounding_box" for rectangular rooms
```

Done! The system will now:
1. Calculate your position using all 3 scanners
2. Determine which room you're in based on learned boundaries
3. Update the Area sensor automatically

---

## How It Works

### Multi-Scanner Position Calculation

**Example:** You're on Floor 2 with your phone

1. **Floor 1 Scanner** sees your phone: RSSI = -75 dB → **4.2 meters away**
2. **Floor 2 Scanner** sees your phone: RSSI = -55 dB → **2.1 meters away**
3. **Floor 3 Scanner** sees your phone: RSSI = -82 dB → **6.8 meters away**

**Old method (minimum distance):**
- Assigns to "Floor 2 area" (closest scanner)
- Can't tell which room on Floor 2

**New method (trilateration):**
- Calculates position: `(x: 2.3, y: 1.5, z: 3.2)` meters
- Z ≈ 3m → You're on Floor 2 ✓
- X, Y position → Checks if inside learned room boundaries
- "You're in the Kitchen!" (based on polygon match)

### Confidence Scoring

The system calculates how well the position fits the distance measurements:
- **> 0.7** = Excellent (trust this position!)
- **0.3 - 0.7** = Good (usable)
- **< 0.3** = Poor (falls back to closest-scanner method)

---

## Services Reference

### `bermuda_tri.set_scanner_position`
Set physical coordinates for a scanner.

**Parameters:**
- `scanner_address` (required): MAC address of scanner
- `x` (required): X coordinate in meters
- `y` (required): Y coordinate in meters
- `z` (required): Z coordinate in meters (floor height)

---

### `bermuda_tri.mark_position`
Record current position as being in a specific room.

**Parameters:**
- `device_address` (required): MAC of tracked device
- `area_id` (required): Home Assistant area (dropdown)

**Usage:** Walk to a room, stand still for 3-5 seconds, then run this service.

---

### `bermuda_tri.calculate_room_boundaries`
Generate room boundary polygons from collected samples.

**Parameters:**
- `method` (optional): `"convex_hull"` (default) or `"bounding_box"`

**Convex Hull:** Best for irregularly shaped rooms
**Bounding Box:** Best for rectangular rooms

---

### `bermuda_tri.clear_room_samples`
Clear position samples.

**Parameters:**
- `area_id` (optional): Specific area to clear (leave empty for all)

---

### `bermuda_tri.export_floor_plan`
Export visualization data (JSON).

**Parameters:**
- `include_history` (optional): Include training samples

**Returns:** JSON with scanner positions, room boundaries, and device positions.

Use this to visualize your setup in tools like matplotlib, Grafana, or custom dashboards!

---

## Troubleshooting

### "Could not calculate position"

**Possible causes:**
- Less than 3 scanners have positions configured
- Scanners not seeing the device
- Check `Scanner Count` sensor (should be ≥ 3)

**Solution:**
1. Verify all scanner positions are set
2. Check that device is being detected (RSSI sensors should have values)
3. Walk closer to scanners

---

### Low Confidence Scores

**Possible causes:**
- Scanners too close together (poor geometry)
- RSSI calibration needed
- Physical obstructions (walls, metal)

**Solution:**
1. Spread scanners apart (different rooms/floors is ideal!)
2. Calibrate `ref_power` and `attenuation` per Bermuda docs
3. Try different `ref_power` values for your environment

---

### Room Detection Not Working

**Possible causes:**
- No room boundaries learned yet
- Not enough training samples
- Position is between rooms

**Solution:**
1. Check room boundaries exist: Run `export_floor_plan` service
2. Collect more samples (5-10 per room minimum)
3. Stand in center of room when marking positions

---

## Advanced: Coordinate System Tips

### Choosing Your Origin (0, 0, 0)

Pick any reference point! Common choices:
- **Front door** of your home
- **First scanner location**
- **Corner of your property**

### Measuring Coordinates

You don't need to be super precise. ±0.5m accuracy is fine!

**Simple method:**
1. Set first scanner at (0, 0, 0)
2. Measure distance to second scanner with tape measure
3. If it's 5m to the right: (5, 0, Z)
4. If it's 3m up (ceiling height): (0, 0, 3)

**For vertical stacking (your 3-floor setup):**
- All scanners at X=0, Y=0
- Only Z changes: Floor 1=0, Floor 2=3, Floor 3=6

---

## Visualization Example

Export your floor plan and visualize in Python:

```python
import json
import matplotlib.pyplot as plt

# Get data from export_floor_plan service
data = {  # ... paste service response
}

# Plot scanners
for scanner in data['scanners']:
    plt.scatter(scanner['x'], scanner['y'], c='red', s=100, marker='^')
    plt.text(scanner['x'], scanner['y'], scanner['name'])

# Plot room boundaries
for room in data['rooms']:
    polygon = room['polygon']
    xs = [p['x'] for p in polygon] + [polygon[0]['x']]
    ys = [p['y'] for p in polygon] + [polygon[0]['y']]
    plt.plot(xs, ys, label=room['room_name'])

# Plot current device position
for device in data['devices']:
    plt.scatter(device['x'], device['y'], c='blue', s=50)

plt.legend()
plt.xlabel('X (meters)')
plt.ylabel('Y (meters)')
plt.title('Bermuda Trilateration Floor Plan')
plt.grid(True)
plt.show()
```

---

## Comparison: Trilateration vs. Min-Distance

| Feature | Min Distance (Original) | Trilateration (This Fork) |
|---------|------------------------|---------------------------|
| **Scanners Used** | 1 (closest only) | 3+ (all simultaneously) |
| **Position Info** | Area only | X, Y, Z coordinates |
| **Room Detection** | Scanner's area | Learned polygon boundaries |
| **Floor Detection** | Manual assignment | Automatic (Z-coordinate) |
| **Accuracy** | ±room size | ±0.5-2 meters |
| **Setup** | Assign scanner areas | Set positions + learn rooms |
| **Min Scanners** | 1 | 3 |

---

## Credits

- **Original Bermuda:** [@agittins](https://github.com/agittins/bermuda)
- **Trilateration Fork:** Community contribution
- **Algorithm:** Least-squares multilateration (Gauss-Newton)

---

## Contributing Back

This is a **proof-of-concept** fork. If it works well, we can propose merging features back to the official Bermuda project!

Please report issues on the fork's GitHub repository.

---

## FAQ

**Q: Can I use just 2 scanners?**
A: No, trilateration needs minimum 3 scanners. With 2, you can only get 2 possible positions (ambiguous).

**Q: Do I need to learn room boundaries?**
A: No! Position calculation works without it. Room learning is optional for automatic area assignment.

**Q: Will this work with Shelly devices?**
A: Yes! Any Bermuda-compatible Bluetooth proxy works.

**Q: Can I mix this with the original Bermuda?**
A: This fork has a different domain (`bermuda_tri`), so you can install both simultaneously!

**Q: What about battery drain on tracked devices?**
A: No change from original Bermuda. Your phone already broadcasts BLE; we just use the signal better.

**Q: How accurate is it?**
A: Typically ±0.5-2 meters with good scanner placement and calibration. RSSI-based positioning has inherent limitations due to signal bounce and interference.

---

Happy Triangulating! 📐
