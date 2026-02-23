import requests
import base64
from django.conf import settings

YOLO_URL = getattr(settings, "YOLO_SERVICE_URL", "http://yolo-service:8001")

def send_frame_to_yolo(base64_image):
    """
    Send base64 image to YOLO service for alignment detection
    """
    payload = {"image": base64_image}
    try:
        resp = requests.post(f"{YOLO_URL}/api/v1/detect", json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {
            "alignment_offset_pixels": 0,
            "alignment_offset_mm": 0,
            "status": "ERROR",
            "error": str(e)
        }