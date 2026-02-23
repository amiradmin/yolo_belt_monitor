import numpy as np
import cv2
from typing import Dict, List, Tuple, Optional
import logging
from dataclasses import dataclass
from scipy import ndimage
import skimage.measure

logger = logging.getLogger(__name__)


@dataclass
class BeltTearStatus:
    """Belt tear status data class"""
    tear_detected: bool
    tear_count: int
    tear_locations: List[Dict[str, any]]
    max_tear_length_mm: float
    max_tear_width_mm: float
    total_tear_area_mm2: float
    severity: str  # 'none', 'minor', 'moderate', 'critical'
    recommendations: List[str]
    confidence: float
    timestamp: float


class BeltTearDetector:
    """Detect tears, rips, and damage on conveyor belt"""

    def __init__(self, belt_width_mm: float = 1200, pixel_to_mm: float = 0.5):
        """
        Initialize belt tear detector

        Args:
            belt_width_mm: Actual belt width in millimeters
            pixel_to_mm: Conversion factor from pixels to millimeters
        """
        self.belt_width_mm = belt_width_mm
        self.pixel_to_mm = pixel_to_mm

        # Tear thresholds
        self.min_tear_length_mm = 10  # Minimum tear length to report
        self.min_tear_width_mm = 2  # Minimum tear width to report

        # Severity thresholds
        self.minor_threshold_mm = 50  # Minor tear < 50mm
        self.moderate_threshold_mm = 150  # Moderate tear < 150mm
        self.critical_threshold_mm = 300  # Critical tear >= 300mm

        # Reference belt texture (for anomaly detection)
        self.reference_texture = None
        self.texture_mean = None
        self.texture_std = None

    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocess image for tear detection
        """
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Enhance contrast using CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Apply bilateral filter to preserve edges while reducing noise
        filtered = cv2.bilateralFilter(enhanced, 9, 75, 75)

        return filtered

    def detect_edges(self, image: np.ndarray) -> np.ndarray:
        """
        Detect edges in the belt image
        """
        # Use Canny edge detection
        edges = cv2.Canny(image, 50, 150)

        # Dilate edges to connect nearby tears
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=1)

        return dilated

    def find_tear_candidates(self, edge_image: np.ndarray) -> List[Dict]:
        """
        Find potential tear regions using contour analysis
        """
        # Find contours
        contours, _ = cv2.findContours(
            edge_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        tear_candidates = []

        for contour in contours:
            # Calculate contour properties
            area = cv2.contourArea(contour)

            # Filter very small contours (noise)
            if area < 50:  # Minimum area in pixels
                continue

            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(contour)

            # Calculate aspect ratio (tears are typically elongated)
            aspect_ratio = max(w, h) / min(w, h) if min(w, h) > 0 else 1

            # Calculate extent (how filled the bounding box is)
            extent = area / (w * h) if w * h > 0 else 0

            # Calculate solidity (how convex/concave)
            hull = cv2.convexHull(contour)
            hull_area = cv2.contourArea(hull)
            solidity = area / hull_area if hull_area > 0 else 0

            # Tears typically have:
            # - High aspect ratio (long and thin)
            # - Low extent (irregular shape)
            # - Low solidity (jagged edges)
            if aspect_ratio > 3 and extent < 0.6 and solidity < 0.8:
                # This looks like a tear

                # Convert to real-world dimensions
                length_mm = max(w, h) * self.pixel_to_mm
                width_mm = min(w, h) * self.pixel_to_mm

                # Only consider if above minimum size
                if length_mm >= self.min_tear_length_mm and width_mm >= self.min_tear_width_mm:
                    tear_candidates.append({
                        'contour': contour,
                        'bbox': (x, y, w, h),
                        'area_pixels': area,
                        'area_mm2': area * (self.pixel_to_mm ** 2),
                        'length_mm': length_mm,
                        'width_mm': width_mm,
                        'aspect_ratio': aspect_ratio,
                        'center': (x + w // 2, y + h // 2)
                    })

        return tear_candidates

    def analyze_texture_anomaly(self, image: np.ndarray, tear_regions: List[Dict]) -> List[Dict]:
        """
        Analyze texture in tear regions to confirm tears
        """
        if self.reference_texture is None:
            # Initialize reference texture from first frame
            self.reference_texture = image
            self.texture_mean = np.mean(image)
            self.texture_std = np.std(image)
            return tear_regions

        confirmed_tears = []

        for tear in tear_regions:
            x, y, w, h = tear['bbox']

            # Extract region
            region = image[y:y + h, x:x + w]

            if region.size == 0:
                continue

            # Calculate texture statistics
            region_mean = np.mean(region)
            region_std = np.std(region)

            # Calculate local binary pattern (simplified)
            # This helps detect tears vs shadows
            gradient_x = cv2.Sobel(region, cv2.CV_64F, 1, 0, ksize=3)
            gradient_y = cv2.Sobel(region, cv2.CV_64F, 0, 1, ksize=3)
            gradient_magnitude = np.sqrt(gradient_x ** 2 + gradient_y ** 2)
            mean_gradient = np.mean(gradient_magnitude)

            # Tears typically have:
            # - Different mean intensity from belt
            # - Higher edge density
            # - Different texture patterns

            intensity_diff = abs(region_mean - self.texture_mean)
            edge_density = mean_gradient / 255

            if intensity_diff > 20 or edge_density > 0.3:
                tear['texture_anomaly'] = True
                tear['intensity_diff'] = intensity_diff
                tear['edge_density'] = edge_density
                confirmed_tears.append(tear)

        return confirmed_tears

    def classify_tear_severity(self, tears: List[Dict]) -> Tuple[str, List[str]]:
        """
        Classify overall tear severity and generate recommendations
        """
        if not tears:
            return "none", ["Belt appears intact. Continue normal operation."]

        # Find maximum tear length
        max_length = max(t['length_mm'] for t in tears)

        # Count tears
        tear_count = len(tears)

        # Calculate total area
        total_area = sum(t['area_mm2'] for t in tears)

        recommendations = []

        # Classify severity
        if max_length >= self.critical_threshold_mm:
            severity = "critical"
            recommendations = [
                "IMMEDIATE ACTION REQUIRED",
                f"Critical tear detected: {max_length:.0f}mm long",
                "Stop conveyor immediately",
                "Replace damaged belt section",
                "Inspect for cause of tear"
            ]
        elif max_length >= self.moderate_threshold_mm or tear_count > 5:
            severity = "moderate"
            recommendations = [
                f"Moderate damage: {tear_count} tears, longest {max_length:.0f}mm",
                "Schedule repair within 24 hours",
                "Monitor tear progression",
                "Reduce belt load until repair"
            ]
        elif max_length >= self.minor_threshold_mm or tear_count > 2:
            severity = "minor"
            recommendations = [
                f"Minor damage detected: {tear_count} small tears",
                "Monitor during next maintenance",
                "Check for causes (sharp objects, worn idlers)",
                "Schedule inspection"
            ]
        else:
            severity = "minor"
            recommendations = [
                "Minor surface wear detected",
                "Continue normal monitoring",
                "Check during routine maintenance"
            ]

        return severity, recommendations

    def analyze_tears(self, image: np.ndarray) -> BeltTearStatus:
        """
        Main method to analyze belt for tears
        """
        try:
            # Preprocess image
            processed = self.preprocess_image(image)

            # Detect edges
            edges = self.detect_edges(processed)

            # Find tear candidates
            candidates = self.find_tear_candidates(edges)

            # Confirm tears with texture analysis
            confirmed_tears = self.analyze_texture_anomaly(processed, candidates)

            if not confirmed_tears:
                return BeltTearStatus(
                    tear_detected=False,
                    tear_count=0,
                    tear_locations=[],
                    max_tear_length_mm=0.0,
                    max_tear_width_mm=0.0,
                    total_tear_area_mm2=0.0,
                    severity="none",
                    recommendations=["Belt appears intact"],
                    confidence=0.95,
                    timestamp=cv2.getTickCount() / cv2.getTickFrequency()
                )

            # Calculate statistics
            tear_count = len(confirmed_tears)
            max_length = max(t['length_mm'] for t in confirmed_tears)
            max_width = max(t['width_mm'] for t in confirmed_tears)
            total_area = sum(t['area_mm2'] for t in confirmed_tears)

            # Classify severity
            severity, recommendations = self.classify_tear_severity(confirmed_tears)

            # Prepare tear locations for reporting
            tear_locations = []
            for tear in confirmed_tears:
                x, y, w, h = tear['bbox']
                tear_locations.append({
                    'x': x,
                    'y': y,
                    'width': w,
                    'height': h,
                    'length_mm': tear['length_mm'],
                    'width_mm': tear['width_mm'],
                    'area_mm2': tear['area_mm2'],
                    'center': tear['center']
                })

            # Calculate confidence based on edge quality and texture analysis
            confidence = min(0.95, 0.7 + (len(confirmed_tears) / 20))

            return BeltTearStatus(
                tear_detected=True,
                tear_count=tear_count,
                tear_locations=tear_locations,
                max_tear_length_mm=round(max_length, 1),
                max_tear_width_mm=round(max_width, 1),
                total_tear_area_mm2=round(total_area, 1),
                severity=severity,
                recommendations=recommendations,
                confidence=round(confidence, 2),
                timestamp=cv2.getTickCount() / cv2.getTickFrequency()
            )

        except Exception as e:
            logger.error(f"Error in tear analysis: {e}")
            return BeltTearStatus(
                tear_detected=False,
                tear_count=0,
                tear_locations=[],
                max_tear_length_mm=0.0,
                max_tear_width_mm=0.0,
                total_tear_area_mm2=0.0,
                severity="error",
                recommendations=["Error in tear detection system"],
                confidence=0.0,
                timestamp=cv2.getTickCount() / cv2.getTickFrequency()
            )

    def visualize_tears(self, image: np.ndarray, status: BeltTearStatus) -> np.ndarray:
        """
        Draw tear visualization on image
        """
        result = image.copy()
        height, width = image.shape[:2]

        if status.tear_detected:
            # Color based on severity
            if status.severity == "minor":
                color = (0, 255, 255)  # Yellow
            elif status.severity == "moderate":
                color = (0, 165, 255)  # Orange
            else:
                color = (0, 0, 255)  # Red

            # Draw each tear
            for tear in status.tear_locations:
                x, y = tear['x'], tear['y']
                w, h = tear['width'], tear['height']

                # Draw bounding box
                cv2.rectangle(result, (x, y), (x + w, y + h), color, 2)

                # Draw center point
                cv2.circle(result, tuple(tear['center']), 3, color, -1)

                # Add tear dimensions
                text = f"{tear['length_mm']:.0f}mm"
                cv2.putText(result, text, (x, y - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

            # Add summary
            cv2.putText(result, f"TEAR DETECTED: {status.tear_count} tears",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

            cv2.putText(result, f"Max length: {status.max_tear_length_mm:.0f}mm",
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1)

            cv2.putText(result, f"Severity: {status.severity.upper()}",
                        (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

            # Add warning for critical tears
            if status.severity == "critical":
                cv2.putText(result, "⚠️ CRITICAL TEAR - STOP CONVEYOR ⚠️",
                            (width // 2 - 250, height // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        else:
            # No tears detected
            cv2.putText(result, "No tears detected",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        return result

    def track_tear_progression(self, current_tears: List[Dict],
                               previous_tears: List[Dict]) -> Dict[str, any]:
        """
        Track how tears are progressing over time
        """
        if not previous_tears or not current_tears:
            return {'progression': 'unknown'}

        # Compare tear counts
        count_change = len(current_tears) - len(previous_tears)

        # Compare max lengths
        current_max = max(t['length_mm'] for t in current_tears) if current_tears else 0
        previous_max = max(t['length_mm'] for t in previous_tears) if previous_tears else 0
        length_change = current_max - previous_max

        # Determine progression
        if count_change > 2 or length_change > 20:
            progression = 'rapid_worsening'
            recommendation = "Immediate inspection required - tear progressing rapidly"
        elif count_change > 0 or length_change > 5:
            progression = 'gradual_worsening'
            recommendation = "Schedule maintenance - tear is slowly progressing"
        elif count_change < 0 or length_change < -5:
            progression = 'improving'
            recommendation = "Tear appears to be stabilizing"
        else:
            progression = 'stable'
            recommendation = "Tear condition stable"

        return {
            'progression': progression,
            'count_change': count_change,
            'length_change_mm': round(length_change, 1),
            'recommendation': recommendation
        }