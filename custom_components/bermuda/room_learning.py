"""
Interactive room boundary learning system.

This module allows users to walk around their home with a tracked device
and mark their current position as being in specific rooms. The system
then learns room boundaries automatically by computing convex hulls or
bounding boxes from the collected position samples.

Usage:
1. User enables training mode
2. User walks to a room and calls mark_position service with room name
3. System records (x, y, z) position
4. After collecting samples, system generates room boundaries
5. Boundaries are stored and used for automatic room detection
"""

from __future__ import annotations

import math
from typing import TypedDict


class Point3D(TypedDict):
    """3D point representation."""

    x: float
    y: float
    z: float


class RoomSample(TypedDict):
    """A recorded position sample for a room."""

    x: float
    y: float
    z: float
    timestamp: float
    room_id: str
    room_name: str
    confidence: float


class RoomBoundary(TypedDict):
    """Room boundary definition."""

    room_id: str
    room_name: str
    polygon: list[Point3D]  # Vertices of boundary polygon (convex hull)
    z_min: float
    z_max: float
    center: Point3D  # Centroid of room
    sample_count: int


def cross_product_2d(o: Point3D, a: Point3D, b: Point3D) -> float:
    """
    Calculate 2D cross product of vectors OA and OB.

    Positive if counter-clockwise turn, negative if clockwise, zero if collinear.
    """
    return (a["x"] - o["x"]) * (b["y"] - o["y"]) - (a["y"] - o["y"]) * (b["x"] - o["x"])


def convex_hull_2d(points: list[Point3D]) -> list[Point3D]:
    """
    Compute convex hull of 2D points using Graham's scan algorithm.

    Args:
        points: List of 3D points (only x, y are used)

    Returns:
        List of points forming convex hull in counter-clockwise order

    This creates the smallest convex polygon containing all points.
    Good for irregularly shaped rooms.
    """
    if len(points) < 3:
        return points

    # Sort points by x-coordinate (and y as tiebreaker)
    sorted_points = sorted(points, key=lambda p: (p["x"], p["y"]))

    # Build lower hull
    lower = []
    for p in sorted_points:
        while len(lower) >= 2 and cross_product_2d(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    # Build upper hull
    upper = []
    for p in reversed(sorted_points):
        while len(upper) >= 2 and cross_product_2d(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    # Remove last point of each half because it's repeated
    return lower[:-1] + upper[:-1]


def bounding_box_2d(points: list[Point3D], margin: float = 0.5) -> list[Point3D]:
    """
    Compute axis-aligned bounding box (rectangle) from points.

    Args:
        points: List of 3D points (only x, y are used)
        margin: Extra margin in meters to add around box

    Returns:
        List of 4 corner points forming rectangle

    This is simpler than convex hull but may be less accurate for
    non-rectangular rooms. Good for typical rectangular rooms.
    """
    if not points:
        return []

    x_coords = [p["x"] for p in points]
    y_coords = [p["y"] for p in points]

    x_min = min(x_coords) - margin
    x_max = max(x_coords) + margin
    y_min = min(y_coords) - margin
    y_max = max(y_coords) + margin

    # Z is average (for display purposes)
    z_avg = sum(p["z"] for p in points) / len(points)

    # Return corners in counter-clockwise order
    return [
        Point3D(x=x_min, y=y_min, z=z_avg),
        Point3D(x=x_max, y=y_min, z=z_avg),
        Point3D(x=x_max, y=y_max, z=z_avg),
        Point3D(x=x_min, y=y_max, z=z_avg),
    ]


def point_in_polygon_2d(point: Point3D, polygon: list[Point3D]) -> bool:
    """
    Test if a point is inside a polygon using ray casting algorithm.

    Args:
        point: Point to test
        polygon: List of vertices forming polygon boundary

    Returns:
        True if point is inside polygon, False otherwise

    This uses the "even-odd rule" ray casting algorithm.
    """
    if len(polygon) < 3:
        return False

    x, y = point["x"], point["y"]
    n = len(polygon)
    inside = False

    p1 = polygon[0]
    for i in range(1, n + 1):
        p2 = polygon[i % n]

        if y > min(p1["y"], p2["y"]):
            if y <= max(p1["y"], p2["y"]):
                if x <= max(p1["x"], p2["x"]):
                    if p1["y"] != p2["y"]:
                        x_intersect = (y - p1["y"]) * (p2["x"] - p1["x"]) / (
                            p2["y"] - p1["y"]
                        ) + p1["x"]

                        if p1["x"] == p2["x"] or x <= x_intersect:
                            inside = not inside

        p1 = p2

    return inside


def calculate_centroid(points: list[Point3D]) -> Point3D:
    """Calculate geometric center of points."""
    if not points:
        return Point3D(x=0.0, y=0.0, z=0.0)

    x_avg = sum(p["x"] for p in points) / len(points)
    y_avg = sum(p["y"] for p in points) / len(points)
    z_avg = sum(p["z"] for p in points) / len(points)

    return Point3D(x=x_avg, y=y_avg, z=z_avg)


def calculate_room_boundary(
    samples: list[RoomSample],
    method: str = "convex_hull",
    z_margin: float = 1.0,
) -> RoomBoundary | None:
    """
    Calculate room boundary from collected position samples.

    Args:
        samples: List of position samples for this room
        method: Boundary calculation method ("convex_hull" or "bounding_box")
        z_margin: Extra margin in meters for Z bounds (floor/ceiling tolerance)

    Returns:
        RoomBoundary or None if insufficient samples
    """
    if len(samples) < 3:
        return None

    # Extract points from samples
    points = [Point3D(x=s["x"], y=s["y"], z=s["z"]) for s in samples]

    # Calculate 2D boundary
    if method == "bounding_box":
        polygon = bounding_box_2d(points, margin=0.5)
    else:  # convex_hull
        polygon = convex_hull_2d(points)

    # Calculate Z bounds (floor height range)
    z_coords = [p["z"] for p in points]
    z_min = min(z_coords) - z_margin
    z_max = max(z_coords) + z_margin

    # Calculate centroid
    center = calculate_centroid(points)

    # Get room info from first sample (they should all be the same room)
    room_id = samples[0]["room_id"]
    room_name = samples[0]["room_name"]

    return RoomBoundary(
        room_id=room_id,
        room_name=room_name,
        polygon=polygon,
        z_min=z_min,
        z_max=z_max,
        center=center,
        sample_count=len(samples),
    )


def detect_room_from_position(
    position: Point3D,
    room_boundaries: list[RoomBoundary],
    z_tolerance: float = 0.5,
) -> RoomBoundary | None:
    """
    Detect which room a position is in based on learned boundaries.

    Args:
        position: Current device position
        room_boundaries: List of learned room boundaries
        z_tolerance: Extra tolerance for Z-coordinate matching (meters)

    Returns:
        RoomBoundary that contains the position, or None if not in any room

    If position is in multiple overlapping rooms (unlikely but possible),
    returns the room whose center is closest to the position.
    """
    matching_rooms = []

    for room in room_boundaries:
        # Check Z bounds first (floor level)
        if not (
            room["z_min"] - z_tolerance <= position["z"] <= room["z_max"] + z_tolerance
        ):
            continue

        # Check if point is in room's 2D polygon
        if point_in_polygon_2d(position, room["polygon"]):
            # Calculate distance to room center for disambiguation
            center = room["center"]
            distance = math.sqrt(
                (position["x"] - center["x"]) ** 2
                + (position["y"] - center["y"]) ** 2
                + (position["z"] - center["z"]) ** 2
            )
            matching_rooms.append((room, distance))

    if not matching_rooms:
        return None

    # Return room with closest center
    matching_rooms.sort(key=lambda x: x[1])
    return matching_rooms[0][0]


def merge_room_samples(
    existing_samples: list[RoomSample],
    new_samples: list[RoomSample],
    max_samples_per_room: int = 100,
) -> list[RoomSample]:
    """
    Merge new position samples with existing ones, keeping most recent.

    Args:
        existing_samples: Previously collected samples
        new_samples: New samples to add
        max_samples_per_room: Maximum samples to keep (oldest are removed)

    Returns:
        Merged list of samples, limited to max count
    """
    all_samples = existing_samples + new_samples

    # Sort by timestamp (newest first)
    all_samples.sort(key=lambda s: s["timestamp"], reverse=True)

    # Keep only most recent samples
    return all_samples[:max_samples_per_room]


def export_room_boundaries_for_visualization(
    room_boundaries: list[RoomBoundary],
) -> dict:
    """
    Export room boundaries in a format suitable for visualization/plotting.

    Returns:
        Dict with rooms and their polygons for JSON export or plotting
    """
    export_data = {
        "rooms": [],
        "bounds": {
            "x_min": float("inf"),
            "x_max": float("-inf"),
            "y_min": float("inf"),
            "y_max": float("-inf"),
            "z_min": float("inf"),
            "z_max": float("-inf"),
        },
    }

    for room in room_boundaries:
        polygon_coords = [
            {"x": p["x"], "y": p["y"], "z": p["z"]} for p in room["polygon"]
        ]

        room_data = {
            "room_id": room["room_id"],
            "room_name": room["room_name"],
            "polygon": polygon_coords,
            "z_min": room["z_min"],
            "z_max": room["z_max"],
            "center": room["center"],
            "sample_count": room["sample_count"],
        }

        export_data["rooms"].append(room_data)

        # Update bounds
        for p in room["polygon"]:
            export_data["bounds"]["x_min"] = min(export_data["bounds"]["x_min"], p["x"])
            export_data["bounds"]["x_max"] = max(export_data["bounds"]["x_max"], p["x"])
            export_data["bounds"]["y_min"] = min(export_data["bounds"]["y_min"], p["y"])
            export_data["bounds"]["y_max"] = max(export_data["bounds"]["y_max"], p["y"])

        export_data["bounds"]["z_min"] = min(
            export_data["bounds"]["z_min"], room["z_min"]
        )
        export_data["bounds"]["z_max"] = max(
            export_data["bounds"]["z_max"], room["z_max"]
        )

    return export_data
