import numpy as np
import cv2
from typing import Dict, Optional, List, Tuple
import logging
from dataclasses import dataclass
from collections import deque
import time

logger = logging.getLogger(__name__)


@dataclass
class BeltSpeedStatus:
    """Belt speed status data class"""
    current_speed_mps: float  # meters per second
    average_speed_mps: float
    speed_percentage: float  # percentage of nominal speed
    is_running: bool
    is_at_nominal: bool
    variation_percentage: float
    direction: str  # 'forward', 'reverse', 'stopped'
    severity: str  # 'normal', 'warning', 'critical'
    confidence: float
    timestamp: float


class BeltSpeedMonitor:
    """Monitor conveyor belt speed"""

    def __init__(self, nominal_speed_mps: float = 1.5,
                 roller_diameter_mm: float = 200,
                 frames_to_average: int = 30):
        """
        Initialize belt speed monitor

        Args:
            nominal_speed_mps: Design belt speed in meters/second
            roller_diameter_mm: Diameter of drive roller in mm
            frames_to_average: Number of frames to average for speed calculation
        """
        self.nominal_speed = nominal_speed_mps
        self.roller_diameter = roller_diameter_mm / 1000  # Convert to meters

        # Speed thresholds (percentage of nominal)
        self.warning_low_threshold = 80  # Below 80% is warning
        self.critical_low_threshold = 50  # Below 50% is critical
        self.warning_high_threshold = 110  # Above 110% is warning
        self.critical_high_threshold = 120  # Above 120% is critical

        # For optical flow calculation
        self.prev_gray = None
        self.feature_params = dict(
            maxCorners=100,
            qualityLevel=0.3,
            minDistance=7,
            blockSize=7
        )
        self.lk_params = dict(
            winSize=(15, 15),
            maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
        )

        # Speed tracking
        self.speed_history = deque(maxlen=frames_to_average)
        self.frame_timestamps = deque(maxlen=frames_to_average)
        self.calibration_factor = None
        self.roller_features = None

    def calibrate(self, reference_image: np.ndarray, known_speed_mps: float):
        """
        Calibrate speed measurement using known speed
        """
        gray = cv2.cvtColor(reference_image, cv2.COLOR_BGR2GRAY)

        # Detect roller or belt features
        features = cv2.goodFeaturesToTrack(gray, mask=None, **self.feature_params)

        if features is not None:
            self.roller_features = features.reshape(-1, 2)
            self.calibration_factor = known_speed_mps  # Store for reference
            logger.info(f"Speed monitor calibrated with {len(features)} features")

    def calculate_speed_optical_flow(self, current_frame: np.ndarray) -> Optional[float]:
        """
        Calculate belt speed using optical flow
        """
        if self.prev_gray is None:
            self.prev_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
            return None

        current_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)

        # Calculate optical flow
        flow = cv2.calcOpticalFlowFarneback(
            self.prev_gray, current_gray, None,
            pyr_scale=0.5, levels=3, winsize=15,
            iterations=3, poly_n=5, poly_sigma=1.2,
            flags=0
        )

        # Calculate average horizontal movement (assuming belt moves horizontally)
        h_flow = flow[..., 0]

        # Filter out noise
        mask = np.abs(h_flow) > 0.5
        if np.sum(mask) > 0:
            avg_h_flow = np.mean(h_flow[mask])
        else:
            avg_h_flow = 0

        self.prev_gray = current_gray

        # Convert pixel displacement to real speed
        # This requires calibration - simplified version
        pixels_per_meter = 1000  # This should be calibrated
        time_delta = 1 / 30  # Assuming 30fps, should be actual timestamp difference

        speed_pixels_per_sec = avg_h_flow / time_delta
        speed_mps = speed_pixels_per_sec / pixels_per_meter

        return speed_mps

    def calculate_speed_feature_tracking(self, current_frame: np.ndarray) -> Optional[float]:
        """
        Calculate belt speed by tracking features
        """
        if self.prev_gray is None or self.roller_features is None:
            self.prev_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)

            # Detect new features
            features = cv2.goodFeaturesToTrack(
                self.prev_gray, mask=None, **self.feature_params
            )
            if features is not None:
                self.roller_features = features.reshape(-1, 2)
            return None

        current_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)

        # Track features
        next_features, status, error = cv2.calcOpticalFlowPyrLK(
            self.prev_gray, current_gray,
            self.roller_features.reshape(-1, 1, 2),
            None, **self.lk_params
        )

        # Select good points
        good_old = self.roller_features[status == 1]
        good_new = next_features[status == 1]

        if len(good_old) > 0:
            # Calculate average displacement
            displacement = good_new - good_old
            avg_displacement = np.mean(displacement, axis=0)

            # Speed calculation (requires calibration)
            # This is a simplified version
            pixels_per_meter = 1000  # Should be calibrated
            time_delta = 1 / 30  # Should be actual timestamp difference

            speed_x_mps = avg_displacement[0] / (pixels_per_meter * time_delta)

            # Update features for next frame
            self.roller_features = good_new

            return abs(speed_x_mps)

        # If tracking lost, detect new features
        features = cv2.goodFeaturesToTrack(
            current_gray, mask=None, **self.feature_params
        )
        if features is not None:
            self.roller_features = features.reshape(-1, 2)

        return None

    def calculate_speed_roller_detection(self, image: np.ndarray) -> Optional[float]:
        """
        Calculate speed by detecting roller rotation
        """
        # This would detect circular features (rollers) and track rotation
        # Simplified implementation
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Detect circles (rollers)
        circles = cv2.HoughCircles(
            gray, cv2.HOUGH_GRADIENT, 1, 20,
            param1=50, param2=30, minRadius=10, maxRadius=50
        )

        if circles is not None and len(circles[0]) > 0:
            # Found rollers - would track rotation here
            # For now, return None as this requires more complex implementation
            pass

        return None

    def analyze_speed(self, image: np.ndarray, timestamp: float) -> BeltSpeedStatus:
        """
        Main method to analyze belt speed
        """
        try:
            # Calculate speed using preferred method
            speed = self.calculate_speed_optical_flow(image)

            if speed is None:
                # Not enough data yet
                return BeltSpeedStatus(
                    current_speed_mps=0.0,
                    average_speed_mps=0.0,
                    speed_percentage=0.0,
                    is_running=False,
                    is_at_nominal=False,
                    variation_percentage=0.0,
                    direction="unknown",
                    severity="warning",
                    confidence=0.0,
                    timestamp=timestamp
                )

            # Store in history
            self.speed_history.append(speed)
            self.frame_timestamps.append(timestamp)

            # Calculate average
            avg_speed = np.mean(self.speed_history) if self.speed_history else 0

            # Calculate percentage of nominal
            if self.nominal_speed > 0:
                speed_percentage = (speed / self.nominal_speed) * 100
                avg_percentage = (avg_speed / self.nominal_speed) * 100
            else:
                speed_percentage = 0
                avg_percentage = 0

            # Determine if running
            is_running = speed > 0.05  # 5 cm/s threshold

            # Determine if at nominal speed
            is_at_nominal = 95 <= speed_percentage <= 105

            # Calculate variation
            variation = np.std(self.speed_history) / avg_speed * 100 if avg_speed > 0 else 0

            # Determine direction (simplified)
            direction = "forward" if speed > 0 else "reverse" if speed < 0 else "stopped"
            speed = abs(speed)

            # Determine severity
            if speed_percentage < self.critical_low_threshold or speed_percentage > self.critical_high_threshold:
                severity = "critical"
            elif speed_percentage < self.warning_low_threshold or speed_percentage > self.warning_high_threshold:
                severity = "warning"
            else:
                severity = "normal"

            # Calculate confidence based on history consistency
            confidence = max(0, 1.0 - (variation / 50))  # Lower variation = higher confidence

            return BeltSpeedStatus(
                current_speed_mps=round(speed, 3),
                average_speed_mps=round(avg_speed, 3),
                speed_percentage=round(speed_percentage, 1),
                is_running=is_running,
                is_at_nominal=is_at_nominal,
                variation_percentage=round(variation, 1),
                direction=direction,
                severity=severity,
                confidence=round(confidence, 2),
                timestamp=timestamp
            )

        except Exception as e:
            logger.error(f"Error in speed analysis: {e}")
            return BeltSpeedStatus(
                current_speed_mps=0.0,
                average_speed_mps=0.0,
                speed_percentage=0.0,
                is_running=False,
                is_at_nominal=False,
                variation_percentage=0.0,
                direction="error",
                severity="critical",
                confidence=0.0,
                timestamp=timestamp
            )

    def visualize_speed(self, image: np.ndarray, status: BeltSpeedStatus) -> np.ndarray:
        """
        Draw speed visualization on image
        """
        result = image.copy()
        height, width = image.shape[:2]

        # Color based on severity
        if status.severity == "normal":
            color = (0, 255, 0)  # Green
        elif status.severity == "warning":
            color = (0, 255, 255)  # Yellow
        else:
            color = (0, 0, 255)  # Red

        # Create speed gauge
        gauge_center = (width - 100, 100)
        gauge_radius = 60

        # Draw gauge background
        cv2.circle(result, gauge_center, gauge_radius, (200, 200, 200), 2)

        # Draw speed indicator
        angle = 180 + (status.speed_percentage / 100) * 180
        angle = min(360, max(180, angle))

        end_x = int(gauge_center[0] + gauge_radius * np.cos(np.radians(angle)))
        end_y = int(gauge_center[1] - gauge_radius * np.sin(np.radians(angle)))

        cv2.line(result, gauge_center, (end_x, end_y), color, 3)

        # Add text
        cv2.putText(result, f"Speed: {status.current_speed_mps:.2f} m/s",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        cv2.putText(result, f"Nominal: {self.nominal_speed:.2f} m/s",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        cv2.putText(result, f"{status.speed_percentage:.1f}%",
                    (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        cv2.putText(result, f"Direction: {status.direction}",
                    (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        # Warning if stopped
        if not status.is_running:
            cv2.putText(result, "⚠️ BELT STOPPED",
                        (width // 2 - 150, height // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)

        return result