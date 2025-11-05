"""
Trilateration algorithms for calculating device positions from multiple scanner distances.

This module implements 2D and 3D multilateration using least-squares optimization.
The algorithms are designed to work with noisy RSSI-based distance measurements
from Bluetooth scanners (ESPHome bluetooth_proxy devices).

References:
- Multilateration: https://en.wikipedia.org/wiki/Multilateration
- Least Squares: https://en.wikipedia.org/wiki/Least_squares
- RSSI-based positioning: https://www.mdpi.com/1424-8220/19/11/2485
"""

from __future__ import annotations

import math
from typing import TypedDict


class ScannerData(TypedDict):
    """Type definition for scanner position and distance data."""

    x: float
    y: float
    z: float
    distance: float
    address: str  # Scanner MAC address for debugging


class PositionResult(TypedDict):
    """Type definition for trilateration result."""

    x: float
    y: float
    z: float | None
    confidence: float  # 0.0 to 1.0
    scanner_count: int
    residual_mean: float  # Average error in meters
    residual_max: float  # Maximum error in meters
    method: str  # "2d" or "3d"


def calculate_distance_3d(
    x1: float, y1: float, z1: float, x2: float, y2: float, z2: float
) -> float:
    """Calculate Euclidean distance between two 3D points."""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)


def calculate_distance_2d(x1: float, y1: float, x2: float, y2: float) -> float:
    """Calculate Euclidean distance between two 2D points."""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def calculate_centroid(scanners: list[ScannerData]) -> tuple[float, float, float]:
    """Calculate the centroid (geometric center) of scanner positions."""
    if not scanners:
        return (0.0, 0.0, 0.0)

    x_sum = sum(s["x"] for s in scanners)
    y_sum = sum(s["y"] for s in scanners)
    z_sum = sum(s["z"] for s in scanners)
    n = len(scanners)

    return (x_sum / n, y_sum / n, z_sum / n)


def calculate_confidence(
    residuals: list[float], distances: list[float], method: str = "gaussian"
) -> float:
    """
    Calculate confidence score (0-1) based on residual errors.

    Args:
        residuals: List of residual errors (difference between measured and calculated distances)
        distances: List of measured distances (for normalization)
        method: Confidence calculation method ("gaussian" or "linear")

    Returns:
        Confidence score from 0.0 (low confidence) to 1.0 (high confidence)

    The confidence score indicates how well the calculated position fits the
    measured distances. Higher scores mean better agreement.
    """
    if not residuals:
        return 0.0

    # Calculate mean absolute residual
    mean_residual = sum(abs(r) for r in residuals) / len(residuals)

    # Normalize by average distance to make confidence scale-independent
    avg_distance = sum(distances) / len(distances) if distances else 1.0
    normalized_residual = mean_residual / avg_distance if avg_distance > 0 else mean_residual

    if method == "gaussian":
        # Gaussian decay: high confidence when residual is small
        # confidence = exp(-(normalized_residual / sigma)^2)
        # sigma = 0.2 means 95% confidence at 5% error
        sigma = 0.2
        confidence = math.exp(-((normalized_residual / sigma) ** 2))
    else:  # linear
        # Linear decay: confidence = max(0, 1 - normalized_residual)
        confidence = max(0.0, 1.0 - normalized_residual)

    return min(1.0, max(0.0, confidence))


def trilaterate_2d(
    scanners: list[ScannerData], max_iterations: int = 10, tolerance: float = 0.01
) -> PositionResult | None:
    """
    Calculate 2D position using multilateration with 3 or more scanners.

    This uses an iterative least-squares approach (Gauss-Newton method) to find
    the position that best fits the measured distances.

    Args:
        scanners: List of scanner data with x, y, z positions and measured distances
        max_iterations: Maximum number of refinement iterations
        tolerance: Convergence tolerance in meters

    Returns:
        PositionResult with x, y coordinates, z=None, and confidence score
        Returns None if insufficient data or calculation fails

    Note:
        For 2D trilateration, we ignore the z-coordinates of scanners and
        calculate only x, y position. This works well when all scanners are
        on approximately the same floor.
    """
    if len(scanners) < 3:
        return None

    # Initial guess: centroid of scanner positions
    x, y, _ = calculate_centroid(scanners)

    # Iterative refinement using Gauss-Newton
    for iteration in range(max_iterations):
        # Build normal equations for least-squares
        # For each scanner i: (x - x_i)^2 + (y - y_i)^2 = d_i^2
        # Linearize around current guess (x, y)

        sum_xx = 0.0
        sum_xy = 0.0
        sum_yy = 0.0
        sum_x = 0.0
        sum_y = 0.0

        for scanner in scanners:
            x_i, y_i = scanner["x"], scanner["y"]
            d_i = scanner["distance"]

            # Calculate current estimated distance
            d_est = calculate_distance_2d(x, y, x_i, y_i)

            if d_est < 0.001:  # Avoid division by zero
                d_est = 0.001

            # Partial derivatives
            dx = (x - x_i) / d_est
            dy = (y - y_i) / d_est

            # Residual: measured - estimated
            residual = d_i - d_est

            # Accumulate normal equations
            sum_xx += dx * dx
            sum_xy += dx * dy
            sum_yy += dy * dy
            sum_x += dx * residual
            sum_y += dy * residual

        # Solve 2x2 system: [sum_xx sum_xy] [delta_x] = [sum_x]
        #                   [sum_xy sum_yy] [delta_y]   [sum_y]

        determinant = sum_xx * sum_yy - sum_xy * sum_xy

        if abs(determinant) < 1e-10:
            # System is singular (scanners are colinear or too close)
            break

        delta_x = (sum_x * sum_yy - sum_y * sum_xy) / determinant
        delta_y = (sum_y * sum_xx - sum_x * sum_xy) / determinant

        # Update position
        x += delta_x
        y += delta_y

        # Check convergence
        if math.sqrt(delta_x**2 + delta_y**2) < tolerance:
            break

    # Calculate residuals and confidence
    residuals = []
    distances = []

    for scanner in scanners:
        d_measured = scanner["distance"]
        d_calculated = calculate_distance_2d(x, y, scanner["x"], scanner["y"])
        residual = d_measured - d_calculated
        residuals.append(residual)
        distances.append(d_measured)

    mean_residual = sum(abs(r) for r in residuals) / len(residuals)
    max_residual = max(abs(r) for r in residuals)
    confidence = calculate_confidence(residuals, distances, method="gaussian")

    return PositionResult(
        x=x,
        y=y,
        z=None,
        confidence=confidence,
        scanner_count=len(scanners),
        residual_mean=mean_residual,
        residual_max=max_residual,
        method="2d",
    )


def trilaterate_3d(
    scanners: list[ScannerData], max_iterations: int = 15, tolerance: float = 0.01
) -> PositionResult | None:
    """
    Calculate 3D position using multilateration with 4 or more scanners.

    This uses an iterative least-squares approach (Gauss-Newton method) to find
    the position that best fits the measured distances in 3D space.

    Args:
        scanners: List of scanner data with x, y, z positions and measured distances
        max_iterations: Maximum number of refinement iterations
        tolerance: Convergence tolerance in meters

    Returns:
        PositionResult with x, y, z coordinates and confidence score
        Returns None if insufficient data or calculation fails

    Note:
        For accurate 3D positioning, scanners should be well-distributed in
        3D space (not coplanar). With 3 scanners, falls back to 2D + estimate.
    """
    if len(scanners) < 3:
        return None

    # With only 3 scanners, we can estimate Z from signal strength but
    # full 3D requires 4+ scanners. For 3 scanners, use 2D method.
    if len(scanners) == 3:
        result_2d = trilaterate_2d(scanners, max_iterations, tolerance)
        if result_2d is None:
            return None

        # Estimate Z as weighted average of scanner Z positions
        # Weight by inverse of distance (closer scanners influence more)
        total_weight = 0.0
        weighted_z = 0.0

        for scanner in scanners:
            if scanner["distance"] > 0:
                weight = 1.0 / scanner["distance"]
                weighted_z += scanner["z"] * weight
                total_weight += weight

        estimated_z = weighted_z / total_weight if total_weight > 0 else scanners[0]["z"]

        result_2d["z"] = estimated_z
        result_2d["method"] = "2d+z_estimate"
        return result_2d

    # Initial guess: centroid of scanner positions
    x, y, z = calculate_centroid(scanners)

    # Iterative refinement using Gauss-Newton
    for iteration in range(max_iterations):
        # Build normal equations for least-squares
        # For each scanner i: (x - x_i)^2 + (y - y_i)^2 + (z - z_i)^2 = d_i^2
        # Linearize around current guess (x, y, z)

        sum_xx = 0.0
        sum_xy = 0.0
        sum_xz = 0.0
        sum_yy = 0.0
        sum_yz = 0.0
        sum_zz = 0.0
        sum_x = 0.0
        sum_y = 0.0
        sum_z = 0.0

        for scanner in scanners:
            x_i, y_i, z_i = scanner["x"], scanner["y"], scanner["z"]
            d_i = scanner["distance"]

            # Calculate current estimated distance
            d_est = calculate_distance_3d(x, y, z, x_i, y_i, z_i)

            if d_est < 0.001:  # Avoid division by zero
                d_est = 0.001

            # Partial derivatives
            dx = (x - x_i) / d_est
            dy = (y - y_i) / d_est
            dz = (z - z_i) / d_est

            # Residual: measured - estimated
            residual = d_i - d_est

            # Accumulate normal equations
            sum_xx += dx * dx
            sum_xy += dx * dy
            sum_xz += dx * dz
            sum_yy += dy * dy
            sum_yz += dy * dz
            sum_zz += dz * dz
            sum_x += dx * residual
            sum_y += dy * residual
            sum_z += dz * residual

        # Solve 3x3 system using Cramer's rule
        # [sum_xx sum_xy sum_xz] [delta_x]   [sum_x]
        # [sum_xy sum_yy sum_yz] [delta_y] = [sum_y]
        # [sum_xz sum_yz sum_zz] [delta_z]   [sum_z]

        # Calculate determinant
        det = (
            sum_xx * (sum_yy * sum_zz - sum_yz * sum_yz)
            - sum_xy * (sum_xy * sum_zz - sum_yz * sum_xz)
            + sum_xz * (sum_xy * sum_yz - sum_yy * sum_xz)
        )

        if abs(det) < 1e-10:
            # System is singular (scanners are coplanar or poorly positioned)
            break

        # Cramer's rule for delta_x
        det_x = (
            sum_x * (sum_yy * sum_zz - sum_yz * sum_yz)
            - sum_xy * (sum_y * sum_zz - sum_yz * sum_z)
            + sum_xz * (sum_y * sum_yz - sum_yy * sum_z)
        )

        # Cramer's rule for delta_y
        det_y = (
            sum_xx * (sum_y * sum_zz - sum_yz * sum_z)
            - sum_x * (sum_xy * sum_zz - sum_yz * sum_xz)
            + sum_xz * (sum_xy * sum_z - sum_y * sum_xz)
        )

        # Cramer's rule for delta_z
        det_z = (
            sum_xx * (sum_yy * sum_z - sum_yz * sum_y)
            - sum_xy * (sum_xy * sum_z - sum_y * sum_xz)
            + sum_x * (sum_xy * sum_yz - sum_yy * sum_xz)
        )

        delta_x = det_x / det
        delta_y = det_y / det
        delta_z = det_z / det

        # Update position
        x += delta_x
        y += delta_y
        z += delta_z

        # Check convergence
        if math.sqrt(delta_x**2 + delta_y**2 + delta_z**2) < tolerance:
            break

    # Calculate residuals and confidence
    residuals = []
    distances = []

    for scanner in scanners:
        d_measured = scanner["distance"]
        d_calculated = calculate_distance_3d(
            x, y, z, scanner["x"], scanner["y"], scanner["z"]
        )
        residual = d_measured - d_calculated
        residuals.append(residual)
        distances.append(d_measured)

    mean_residual = sum(abs(r) for r in residuals) / len(residuals)
    max_residual = max(abs(r) for r in residuals)
    confidence = calculate_confidence(residuals, distances, method="gaussian")

    return PositionResult(
        x=x,
        y=y,
        z=z,
        confidence=confidence,
        scanner_count=len(scanners),
        residual_mean=mean_residual,
        residual_max=max_residual,
        method="3d",
    )


def trilaterate(
    scanners: list[ScannerData],
    prefer_3d: bool = True,
    min_confidence: float = 0.3,
) -> PositionResult | None:
    """
    Automatically choose between 2D and 3D trilateration based on scanner count and geometry.

    Args:
        scanners: List of scanner data with positions and distances
        prefer_3d: If True, attempt 3D when 4+ scanners available
        min_confidence: Minimum acceptable confidence score

    Returns:
        Best PositionResult or None if confidence too low

    This is the main entry point for trilateration. It automatically
    selects the best algorithm based on available scanners.
    """
    if len(scanners) < 3:
        return None

    # Try 3D if we have enough scanners and it's preferred
    if prefer_3d and len(scanners) >= 4:
        result = trilaterate_3d(scanners)
        if result and result["confidence"] >= min_confidence:
            return result

    # Fall back to 2D
    result = trilaterate_2d(scanners)
    if result and result["confidence"] >= min_confidence:
        return result

    # If 2D fails or has low confidence, try 3D as last resort (if we have 4+ scanners)
    if len(scanners) >= 4:
        result = trilaterate_3d(scanners)
        if result and result["confidence"] >= min_confidence:
            return result

    return None  # All methods failed or had too low confidence
