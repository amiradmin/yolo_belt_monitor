from rest_framework.decorators import api_view
from rest_framework.response import Response
import base64
import numpy as np
import cv2
from .utils import send_frame_to_yolo

@api_view(["POST"])
def stream_frame(request):
    image_data = request.data.get("image")

    if not image_data:
        return Response({"error": "No image provided"}, status=400)

    try:
        # Decode base64 image
        header, encoded = image_data.split(",", 1)
        image_bytes = base64.b64decode(encoded)
        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        # TEMP ALIGNMENT LOGIC (TEST MODE)
        alignment_offset_pixels = 25  # simulate detection
        pixels_to_mm_ratio = 0.5
        alignment_offset_mm = alignment_offset_pixels * pixels_to_mm_ratio

        if abs(alignment_offset_mm) < 5:
            status = "OK"
        elif abs(alignment_offset_mm) < 15:
            status = "WARNING"
        else:
            status = "CRITICAL"

        return Response({
            "alignment_offset_pixels": alignment_offset_pixels,
            "alignment_offset_mm": round(alignment_offset_mm, 2),
            "status": status
        })

    except Exception as e:
        return Response({"error": str(e)}, status=500)