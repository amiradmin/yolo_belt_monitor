import cv2
import numpy as np
import logging
from dataclasses import dataclass
from typing import Dict, Tuple, Optional
from collections import deque
import time

logger = logging.getLogger(__name__)


@dataclass
class BeltStatus:
    """Belt monitoring status"""
    alignment_percentage: float
    alignment_direction: str
    alignment_severity: str
    speed_mps: float
    speed_percentage: float
    is_moving: bool
    speed_severity: str
    timestamp: float
    alert: Optional[str] = None


class BeltMonitor:
    def __init__(self, belt_width_mm: float = 1200, nominal_speed_mps: float = 1.5):
        self.belt_width_mm = belt_width_mm
        self.nominal_speed = nominal_speed_mps

        # Thresholds
        self.alignment_warning = 5.0
        self.alignment_critical = 10.0
        self.speed_warning_low = 80
        self.speed_critical_low = 50
        self.speed_warning_high = 110
        self.speed_critical_high = 120

        # State
        self.prev_gray = None
        self.prev_time = time.time()
        self.speed_history = deque(maxlen=30)
        self.pixels_per_meter = None
        self.belt_edges_detected = False

        logger.info(f"BeltMonitor initialized")

    def detect_belt_edges(self, image: np.ndarray) -> Tuple[Optional[int], Optional[int]]:
        """Detect left and right edges of the belt"""
        try:
            height, width = image.shape[:2]
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 150)

            lines = cv2.HoughLinesP(
                edges, rho=1, theta=np.pi / 180, threshold=100,
                minLineLength=height // 3, maxLineGap=50
            )

            if lines is None:
                return None, None

            left_candidates = []
            right_candidates = []
            center_x = width // 2

            for line in lines:
                x1, y1, x2, y2 = line[0]
                if x2 - x1 != 0:
                    slope = (y2 - y1) / (x2 - x1)
                    if abs(slope) > 2:
                        line_x = (x1 + x2) / 2
                        if line_x < center_x - 50:
                            left_candidates.append(line_x)
                        elif line_x > center_x + 50:
                            right_candidates.append(line_x)

            left_edge = int(np.mean(left_candidates)) if left_candidates else None
            right_edge = int(np.mean(right_candidates)) if right_candidates else None

            if left_edge and right_edge:
                self.belt_edges_detected = True
                belt_width_pixels = right_edge - left_edge
                self.pixels_per_meter = belt_width_pixels / (self.belt_width_mm / 1000)

            return left_edge, right_edge

        except Exception as e:
            logger.error(f"Edge detection error: {e}")
            return None, None

    def analyze_alignment(self, image: np.ndarray) -> Dict:
        height, width = image.shape[:2]
        center_x = width // 2
        left_edge, right_edge = self.detect_belt_edges(image)

        if left_edge is None or right_edge is None:
            return {'detected': False, 'percentage': 0, 'direction': 'unknown', 'severity': 'unknown'}

        belt_center = (left_edge + right_edge) // 2
        deviation_pixels = belt_center - center_x
        deviation_percentage = (abs(deviation_pixels) / (width / 2)) * 100

        if deviation_pixels < -5:
            direction = 'left'
        elif deviation_pixels > 5:
            direction = 'right'
        else:
            direction = 'center'

        if deviation_percentage < self.alignment_warning:
            severity = 'normal'
        elif deviation_percentage < self.alignment_critical:
            severity = 'warning'
        else:
            severity = 'critical'

        return {
            'detected': True,
            'percentage': round(deviation_percentage, 1),
            'direction': direction,
            'severity': severity,
            'left_edge': left_edge,
            'right_edge': right_edge,
            'belt_center': belt_center
        }

    def calculate_speed(self, image: np.ndarray) -> float:
        if self.pixels_per_meter is None:
            return 0.0

        current_time = time.time()
        time_delta = current_time - self.prev_time
        current_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        if self.prev_gray is None:
            self.prev_gray = current_gray
            self.prev_time = current_time
            return 0.0

        flow = cv2.calcOpticalFlowFarneback(
            self.prev_gray, current_gray, None,
            pyr_scale=0.5, levels=3, winsize=15,
            iterations=3, poly_n=5, poly_sigma=1.2,
            flags=0
        )

        h_flow = flow[..., 0]
        mask = np.abs(h_flow) > 0.5
        avg_flow = np.mean(h_flow[mask]) if np.sum(mask) > 0 else 0

        if time_delta > 0:
            pixels_per_sec = avg_flow / time_delta
            speed_mps = abs(pixels_per_sec / self.pixels_per_meter)
        else:
            speed_mps = 0

        self.prev_gray = current_gray
        self.prev_time = current_time
        self.speed_history.append(speed_mps)

        return speed_mps

    def analyze_speed(self, speed_mps: float) -> Dict:
        speed_percentage = (speed_mps / self.nominal_speed) * 100 if self.nominal_speed > 0 else 0
        is_moving = speed_mps > 0.05

        if speed_percentage < self.speed_critical_low or speed_percentage > self.speed_critical_high:
            severity = 'critical'
        elif speed_percentage < self.speed_warning_low or speed_percentage > self.speed_warning_high:
            severity = 'warning'
        else:
            severity = 'normal'

        return {
            'speed_mps': round(speed_mps, 2),
            'percentage': round(speed_percentage, 1),
            'is_moving': is_moving,
            'severity': severity
        }

    def analyze_frame(self, image: np.ndarray) -> BeltStatus:
        timestamp = time.time()
        alert = None

        alignment = self.analyze_alignment(image)
        speed_mps = self.calculate_speed(image)
        speed = self.analyze_speed(speed_mps)

        if alignment.get('severity') == 'critical':
            alert = f"CRITICAL: Belt misaligned {alignment['percentage']}% to the {alignment['direction']}"
        elif alignment.get('severity') == 'warning':
            alert = f"WARNING: Belt drifting {alignment['direction']} ({alignment['percentage']}% deviation)"
        elif speed['severity'] == 'critical':
            alert = f"CRITICAL: Belt speed {speed['percentage']}% of nominal"
        elif speed['severity'] == 'warning' and speed['is_moving']:
            alert = f"WARNING: Speed variation ({speed['percentage']}% of nominal)"
        elif not speed['is_moving'] and self.belt_edges_detected:
            alert = "ALERT: Belt stopped"

        return BeltStatus(
            alignment_percentage=alignment.get('percentage', 0),
            alignment_direction=alignment.get('direction', 'unknown'),
            alignment_severity=alignment.get('severity', 'unknown'),
            speed_mps=speed['speed_mps'],
            speed_percentage=speed['percentage'],
            is_moving=speed['is_moving'],
            speed_severity=speed['severity'],
            timestamp=timestamp,
            alert=alert
        )

    def visualize(self, image: np.ndarray, status: BeltStatus) -> np.ndarray:
        result = image.copy()
        height, width = image.shape[:2]
        center_x = width // 2

        # Draw center line
        cv2.line(result, (center_x, 0), (center_x, height), (255, 255, 255), 2)

        # Draw belt edges if detected
        left_edge, right_edge = self.detect_belt_edges(image)
        if left_edge and right_edge:
            cv2.line(result, (left_edge, 0), (left_edge, height), (0, 255, 0), 2)
            cv2.line(result, (right_edge, 0), (right_edge, height), (0, 255, 0), 2)

            belt_center = (left_edge + right_edge) // 2
            if status.alignment_severity == 'normal':
                color = (0, 255, 0)
            elif status.alignment_severity == 'warning':
                color = (0, 255, 255)
            else:
                color = (0, 0, 255)

            cv2.line(result, (belt_center, 0), (belt_center, height), color, 3)

        # Add text overlay
        overlay = result.copy()
        cv2.rectangle(overlay, (10, 10), (350, 130), (0, 0, 0), -1)
        result = cv2.addWeighted(overlay, 0.7, result, 0.3, 0)

        cv2.putText(result, f"Alignment: {status.alignment_percentage:.1f}% {status.alignment_direction}",
                    (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(result, f"Speed: {status.speed_mps:.2f} m/s ({status.speed_percentage:.0f}%)",
                    (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(result, f"Status: {'MOVING' if status.is_moving else 'STOPPED'}",
                    (20, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # Alert
        if status.alert:
            cv2.rectangle(result, (0, 0), (width, 40), (0, 0, 255), -1)
            cv2.putText(result, f"⚠️ {status.alert}", (20, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        return result

    def reset(self):
        self.prev_gray = None
        self.speed_history.clear()
        logger.info("BeltMonitor reset")