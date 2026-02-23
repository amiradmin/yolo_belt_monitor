from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
import cv2
import numpy as np
import io
import logging
from datetime import datetime

from app.models.belt_monitor import BeltMonitor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Conveyor Belt Monitoring System")

# Initialize belt monitor
belt_monitor = BeltMonitor(
    belt_width_mm=1200,
    nominal_speed_mps=1.5
)


@app.get("/")
async def root():
    return {
        "message": "Conveyor Belt Monitoring System",
        "version": "1.0",
        "features": ["belt_alignment", "belt_speed"],
        "status": "active"
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "belt_monitor": "initialized"
    }


@app.post("/analyze")
async def analyze_belt(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if image is None:
            raise HTTPException(status_code=400, detail="Invalid image file")

        status = belt_monitor.analyze_frame(image)

        return JSONResponse({
            "timestamp": datetime.now().isoformat(),
            "filename": file.filename,
            "alignment": {
                "deviation_percentage": status.alignment_percentage,
                "direction": status.alignment_direction,
                "severity": status.alignment_severity
            },
            "speed": {
                "meters_per_second": status.speed_mps,
                "percentage_of_nominal": status.speed_percentage,
                "is_moving": status.is_moving,
                "severity": status.speed_severity
            },
            "alert": status.alert
        })

    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/visualize")
async def visualize_belt(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if image is None:
            raise HTTPException(status_code=400, detail="Invalid image file")

        status = belt_monitor.analyze_frame(image)
        annotated = belt_monitor.visualize(image, status)

        _, buffer = cv2.imencode('.jpg', annotated)

        return StreamingResponse(
            io.BytesIO(buffer.tobytes()),
            media_type="image/jpeg",
            headers={
                "X-Alignment": f"{status.alignment_percentage}% {status.alignment_direction}",
                "X-Speed": f"{status.speed_mps} m/s",
                "X-Alert": status.alert or "none"
            }
        )

    except Exception as e:
        logger.error(f"Visualization error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reset")
async def reset_monitor():
    belt_monitor.reset()
    return {"message": "Belt monitor reset successfully"}