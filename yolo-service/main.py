# yolo-service/main.py
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
from PIL import Image
import io
import redis
import json
import os
from ultralytics import YOLO
import asyncio
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="YOLOv8 Conveyor Monitoring Service")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis connection
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    decode_responses=True
)

# Load YOLO model
MODEL_PATH = os.getenv('MODEL_PATH', 'models/best.pt')
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD', 0.5))

try:
    model = YOLO(MODEL_PATH)
    logger.info(f"Model loaded successfully from {MODEL_PATH}")
except Exception as e:
    logger.warning(f"Could not load custom model, loading default: {e}")
    model = YOLO('yolov8n.pt')


@app.get("/")
async def root():
    return {"message": "YOLOv8 Conveyor Monitoring Service", "status": "active"}


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "model_loaded": model is not None,
        "redis_connected": redis_client.ping()
    }


@app.post("/detect/image")
async def detect_image(file: UploadFile = File(...)):
    """
    Detect objects in a single image
    """
    try:
        # Read image
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # Run inference
        results = model(img, conf=CONFIDENCE_THRESHOLD)

        # Process results
        detections = []
        for r in results:
            boxes = r.boxes
            for box in boxes:
                detection = {
                    'class': model.names[int(box.cls[0])],
                    'confidence': float(box.conf[0]),
                    'bbox': box.xyxy[0].tolist()
                }
                detections.append(detection)

        # Log detection event
        detection_event = {
            'timestamp': datetime.now().isoformat(),
            'filename': file.filename,
            'detections': detections,
            'total_count': len(detections)
        }

        # Store in Redis for monitoring
        redis_client.lpush('detection_logs', json.dumps(detection_event))
        redis_client.ltrim('detection_logs', 0, 999)  # Keep last 1000 logs

        return JSONResponse({
            'success': True,
            'detections': detections,
            'count': len(detections)
        })

    except Exception as e:
        logger.error(f"Error processing image: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/detect/video-frame")
async def detect_video_frame(file: UploadFile = File(...)):
    """
    Process a single frame from video stream
    """
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # Run inference
        results = model(img, conf=CONFIDENCE_THRESHOLD)

        # Draw detections on image
        annotated_frame = results[0].plot()

        # Encode back to bytes
        _, buffer = cv2.imencode('.jpg', annotated_frame)

        return JSONResponse({
            'success': True,
            'detections': len(results[0].boxes),
            'image': buffer.tobytes().hex()  # Convert to hex for JSON transmission
        })

    except Exception as e:
        logger.error(f"Error processing frame: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/detect/jam-detection")
async def detect_jam(file: UploadFile = File(...)):
    """
    Specialized endpoint for jam detection
    """
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        results = model(img, conf=CONFIDENCE_THRESHOLD)

        # Check for jam conditions
        jam_detected = False
        jam_confidence = 0.0

        for r in results:
            boxes = r.boxes
            for box in boxes:
                class_name = model.names[int(box.cls[0])]
                if class_name.lower() in ['jam', 'blockage', 'pileup']:
                    jam_detected = True
                    jam_confidence = float(box.conf[0])
                    break

        # If jam detected, store alert in Redis
        if jam_detected:
            alert = {
                'timestamp': datetime.now().isoformat(),
                'type': 'JAM_DETECTED',
                'confidence': jam_confidence,
                'frame': file.filename
            }
            redis_client.publish('alerts', json.dumps(alert))

            # Store in Redis list for history
            redis_client.lpush('jam_alerts', json.dumps(alert))
            redis_client.ltrim('jam_alerts', 0, 99)  # Keep last 100 alerts

        return JSONResponse({
            'success': True,
            'jam_detected': jam_detected,
            'confidence': jam_confidence,
            'total_detections': len(results[0].boxes)
        })

    except Exception as e:
        logger.error(f"Error in jam detection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_stats():
    """
    Get processing statistics
    """
    try:
        jam_count = redis_client.llen('jam_alerts')
        recent_jams = [json.loads(j) for j in redis_client.lrange('jam_alerts', 0, 10)]

        return JSONResponse({
            'total_jams_detected': jam_count,
            'recent_jams': recent_jams,
            'model_info': {
                'name': model.model_name,
                'task': model.task,
                'names': model.names
            }
        })
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return JSONResponse({'error': str(e)})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)