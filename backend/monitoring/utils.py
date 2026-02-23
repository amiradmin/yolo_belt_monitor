import cv2
import numpy as np
import logging
from datetime import datetime
from io import BytesIO
from django.core.files.base import ContentFile
from PIL import Image

logger = logging.getLogger(__name__)


def capture_frame_from_rtsp(rtsp_url, timeout=10):
    """
    Capture a single frame from RTSP stream
    """
    try:
        cap = cv2.VideoCapture(rtsp_url)
        cap.set(cv2.CAP_PROP_TIMEOUT_MSEC, timeout * 1000)

        ret, frame = cap.read()
        cap.release()

        if ret and frame is not None:
            return frame
        else:
            logger.error(f"Failed to capture frame from {rtsp_url}")
            return None
    except Exception as e:
        logger.error(f"Error capturing frame: {e}")
        return None


def create_thumbnail(image_file, size=(320, 240)):
    """
    Create a thumbnail from an image file
    """
    try:
        img = Image.open(image_file)
        img.thumbnail(size, Image.Resampling.LANCZOS)

        thumb_io = BytesIO()
        img.save(thumb_io, format='JPEG', quality=85)

        return ContentFile(thumb_io.getvalue(), name='thumbnail.jpg')
    except Exception as e:
        logger.error(f"Error creating thumbnail: {e}")
        return None


def draw_detections(image, detections):
    """
    Draw bounding boxes on image
    """
    if image is None or not detections:
        return image

    img_copy = image.copy()

    for detection in detections:
        # Get detection data
        class_name = detection.get('class', 'unknown')
        confidence = detection.get('confidence', 0)
        bbox = detection.get('bbox', [])

        if bbox and len(bbox) == 4:
            x1, y1, x2, y2 = map(int, bbox)

            # Choose color based on class
            if 'jam' in class_name.lower():
                color = (0, 0, 255)  # Red for jam
            else:
                color = (0, 255, 0)  # Green for normal

            # Draw rectangle
            cv2.rectangle(img_copy, (x1, y1), (x2, y2), color, 2)

            # Draw label
            label = f"{class_name}: {confidence:.2f}"
            cv2.putText(img_copy, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    return img_copy


def check_jam_condition(detections, threshold=0.5):
    """
    Check if detections indicate a jam
    """
    if not detections:
        return False, 0.0

    jam_keywords = ['jam', 'blockage', 'pile', 'obstruction', 'congestion']
    jam_confidence = 0.0

    for detection in detections:
        class_name = detection.get('class', '').lower()
        confidence = detection.get('confidence', 0)

        if any(keyword in class_name for keyword in jam_keywords):
            jam_confidence = max(jam_confidence, confidence)

    return jam_confidence > threshold, jam_confidence


def format_detection_results(results):
    """
    Format YOLO detection results for database storage
    """
    formatted = []

    for result in results:
        formatted.append({
            'class': result.get('class', 'unknown'),
            'confidence': float(result.get('confidence', 0)),
            'bbox': result.get('bbox', [])
        })

    return formatted


def get_camera_health_status(camera):
    """
    Get health status summary for a camera
    """
    try:
        latest = camera.health_logs.latest('created_at')

        return {
            'is_online': latest.is_online,
            'fps': latest.fps_actual,
            'last_check': latest.created_at,
            'success_rate': (latest.successful_connections / latest.connection_attempts
                             if latest.connection_attempts > 0 else 0),
            'error': latest.error_message if not latest.is_online else None
        }
    except Exception:
        return {
            'is_online': False,
            'fps': 0,
            'last_check': None,
            'success_rate': 0,
            'error': 'No health data available'
        }