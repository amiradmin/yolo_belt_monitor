import numpy as np
import cv2
from typing import Dict, List, Tuple, Optional
import logging
from dataclasses import dataclass
import math

logger = logging.getLogger(__name__)


@dataclass
class BeltAlignmentStatus:
    """Belt alignment status data class"""
    is_aligned: bool
    deviation_percentage: float
    deviation_mm: float
    direction: str  # 'left', 'right', 'center'
    severity: str  # 'normal', 'warning', 'critical'
    confidence: float
    timestamp: float


class BeltAlignmentDetector:
    """Detect conveyor belt alignment/misalignment"""

    def __init__(self, belt_width_mm: float = 1200, camera_fov_degrees: float = 60):
        """
        Initialize belt alignment detector

        Args:
            belt_width_mm: Actual belt width in millimeters
            camera_fov_degrees: Camera field of view in degrees
        """
        self.belt_width_mm = belt_width_mm
        self.camera_fov = camera_fov_degrees
        self.calibration_factor = None
        self.reference_edges = None
        self.belt_center_line = None

        # Alignment thresholds
        self.warning_threshold = 5.0  # 5% deviation warning
        self.critical_threshold = 10.0  # 10% deviation critical

    def detect_belt_edges(self, image: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Detect left and right edges of the conveyor belt

        Returns:
            Tuple of (left_edge_points, right_edge_points)
        """
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # Apply Gaussian blur to reduce noise
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)

            # Use Canny edge detection
            edges = cv2.Canny(blurred, 50, 150)

            # Use Hough transform to find lines
            lines = cv2.HoughLinesP(
                edges,
                rho=1,
                theta=np.pi / 180,
                threshold=100,
                minLineLength=100,
                maxLineGap=50
            )

            if lines is None:
                return None, None

            # Separate lines into left and right edges based on slope and position
            left_edges = []
            right_edges = []
            height, width = image.shape[:2]
            center_x = width // 2

            for line in lines:
                x1, y1, x2, y2 = line[0]

                # Calculate line slope
                if x2 - x1 != 0:
                    slope = (y2 - y1) / (x2 - x1)

                    # Filter for near-vertical lines (belt edges)
                    if abs(slope) > 2:  # Near vertical
                        line_center_x = (x1 + x2) / 2

                        if line_center_x < center_x - 50:  # Left side
                            left_edges.append(line[0])
                        elif line_center_x > center_x + 50:  # Right side
                            right_edges.append(line[0])

            # Average the edges
            left_edge = np.mean(left_edges, axis=0) if left_edges else None
            right_edge = np.mean(right_edges, axis=0) if right_edges else None

            return left_edge, right_edge

        except Exception as e:
            logger.error(f"Error detecting belt edges: {e}")
            return None, None

    def calculate_belt_center(self, left_edge: np.ndarray, right_edge: np.ndarray) -> Optional[float]:
        """
        Calculate belt center line based on detected edges
        """
        if left_edge is None or right_edge is None:
            return None

        # Calculate center points
        left_center_x = (left_edge[0] + left_edge[2]) / 2
        right_center_x = (right_edge[0] + right_edge[2]) / 2

        # Belt center is midpoint between edges
        belt_center = (left_center_x + right_center_x) / 2

        return belt_center

    def calculate_deviation(self, belt_center: float, image_width: int) -> Dict[str, float]:
        """
        Calculate belt deviation from center

        Returns:
            Dictionary with deviation metrics
        """
        ideal_center = image_width / 2

        # Pixel deviation
        pixel_deviation = belt_center - ideal_center

        # Convert to percentage of half-width
        deviation_percentage = (abs(pixel_deviation) / (image_width / 2)) * 100

        # Estimate real-world deviation in mm
        # Assuming 1 pixel = (belt_width_mm / image_width) mm
        pixel_to_mm = self.belt_width_mm / image_width
        deviation_mm = pixel_deviation * pixel_to_mm

        # Determine direction
        if pixel_deviation < -5:
            direction = "left"
        elif pixel_deviation > 5:
            direction = "right"
        else:
            direction = "center"

        # Determine severity
        if deviation_percentage < self.warning_threshold:
            severity = "normal"
        elif deviation_percentage < self.critical_threshold:
            severity = "warning"
        else:
            severity = "critical"

        return {
            'pixel_deviation': pixel_deviation,
            'deviation_percentage': deviation_percentage,
            'deviation_mm': deviation_mm,
            'direction': direction,
            'severity': severity
        }

    def detect_misalignment_cause(self, image: np.ndarray, edges: Tuple) -> List[str]:
        """
        Detect potential causes of misalignment
        """
        causes = []
        left_edge, right_edge = edges

        if left_edge is None or right_edge is None:
            return ["Edge detection failed"]

        # Check for stuck material on edges
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Sample regions near edges
        height, width = image.shape[:2]

        # Check left edge region
        left_region = gray[:, :50]
        left_brightness = np.mean(left_region)

        # Check right edge region
        right_region = gray[:, -50:]
        right_brightness = np.mean(right_region)

        if left_brightness < 30:  # Dark region might indicate buildup
            causes.append("Possible material buildup on left edge")
        if right_brightness < 30:
            causes.append("Possible material buildup on right edge")

        # Check for uneven lighting (might indicate belt damage)
        top_brightness = np.mean(gray[:50, :])
        bottom_brightness = np.mean(gray[-50:, :])

        if abs(top_brightness - bottom_brightness) > 50:
            causes.append("Uneven illumination - check lighting conditions")

        return causes

    def analyze_alignment(self, image: np.ndarray) -> BeltAlignmentStatus:
        """
        Main method to analyze belt alignment
        """
        try:
            # Detect belt edges
            left_edge, right_edge = self.detect_belt_edges(image)

            if left_edge is None or right_edge is None:
                return BeltAlignmentStatus(
                    is_aligned=False,
                    deviation_percentage=100.0,
                    deviation_mm=self.belt_width_mm / 2,
                    direction="unknown",
                    severity="critical",
                    confidence=0.0,
                    timestamp=cv2.getTickCount() / cv2.getTickFrequency()
                )

            # Calculate belt center
            belt_center = self.calculate_belt_center(left_edge, right_edge)
            image_height, image_width = image.shape[:2]

            # Calculate deviation
            deviation = self.calculate_deviation(belt_center, image_width)

            # Determine if aligned (deviation < warning threshold)
            is_aligned = deviation['deviation_percentage'] < self.warning_threshold

            # Calculate confidence based on edge detection quality
            confidence = self._calculate_confidence(left_edge, right_edge)

            return BeltAlignmentStatus(
                is_aligned=is_aligned,
                deviation_percentage=deviation['deviation_percentage'],
                deviation_mm=abs(deviation['deviation_mm']),
                direction=deviation['direction'],
                severity=deviation['severity'],
                confidence=confidence,
                timestamp=cv2.getTickCount() / cv2.getTickFrequency()
            )

        except Exception as e:
            logger.error(f"Error in alignment analysis: {e}")
            return BeltAlignmentStatus(
                is_aligned=False,
                deviation_percentage=100.0,
                deviation_mm=0.0,
                direction="error",
                severity="critical",
                confidence=0.0,
                timestamp=cv2.getTickCount() / cv2.getTickFrequency()
            )

    def _calculate_confidence(self, left_edge: np.ndarray, right_edge: np.ndarray) -> float:
        """Calculate confidence in edge detection"""
        if left_edge is None or right_edge is None:
            return 0.0

        # Check edge consistency (should be relatively straight)
        left_dx = left_edge[2] - left_edge[0]
        left_dy = left_edge[3] - left_edge[1]
        left_angle = abs(math.atan2(left_dy, left_dx)) if left_dx != 0 else 0

        right_dx = right_edge[2] - right_edge[0]
        right_dy = right_edge[3] - right_edge[1]
        right_angle = abs(math.atan2(right_dy, right_dx)) if right_dx != 0 else 0

        # Good edges should be nearly vertical (angle near 90 degrees or 1.57 radians)
        left_quality = 1.0 - min(abs(left_angle - 1.57), 1.57) / 1.57
        right_quality = 1.0 - min(abs(right_angle - 1.57), 1.57) / 1.57

        return (left_quality + right_quality) / 2

    def visualize_alignment(self, image: np.ndarray, status: BeltAlignmentStatus) -> np.ndarray:
        """
        Draw alignment visualization on image
        """
        result = image.copy()
        height, width = image.shape[:2]

        # Draw center line
        center_x = width // 2
        cv2.line(result, (center_x, 0), (center_x, height), (255, 255, 255), 2)

        # Draw belt center if available
        if status.direction != "unknown":
            # Color based on severity
            if status.severity == "normal":
                color = (0, 255, 0)  # Green
            elif status.severity == "warning":
                color = (0, 255, 255)  # Yellow
            else:
                color = (0, 0, 255)  # Red

            # Calculate belt center position
            pixel_deviation = (status.deviation_percentage / 100) * (width / 2)
            if status.direction == "left":
                belt_center_x = center_x - pixel_deviation
            elif status.direction == "right":
                belt_center_x = center_x + pixel_deviation
            else:
                belt_center_x = center_x

            # Draw belt center line
            cv2.line(result, (int(belt_center_x), 0), (int(belt_center_x), height), color, 3)

            # Add text
            text = f"Deviation: {status.deviation_percentage:.1f}% ({status.direction})"
            cv2.putText(result, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        1, color, 2)

            # Add severity
            cv2.putText(result, f"Severity: {status.severity}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        return result