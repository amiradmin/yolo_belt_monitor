import React, { useRef, useState, useEffect } from "react";
import axios from "axios";

function App() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);

  const [mode, setMode] = useState("upload");
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [streaming, setStreaming] = useState(false);
  const [loading, setLoading] = useState(false);

  const API_URL = "http://localhost:8000";

  // =============================
  // WEBCAM
  // =============================

  const startWebcam = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      videoRef.current.srcObject = stream;
      videoRef.current.play();
      setStreaming(true);
    } catch (err) {
      alert("Cannot access webcam");
    }
  };

  const stopWebcam = () => {
    const stream = videoRef.current?.srcObject;
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
    }
    setStreaming(false);
  };

  const captureWebcamFrame = async () => {
    if (!videoRef.current) return;

    const canvas = document.createElement("canvas");
    canvas.width = videoRef.current.videoWidth;
    canvas.height = videoRef.current.videoHeight;

    const ctx = canvas.getContext("2d");
    ctx.drawImage(videoRef.current, 0, 0);

    const imageBase64 = canvas.toDataURL("image/jpeg");
    await sendFrame(imageBase64);
  };

  useEffect(() => {
    let interval;
    if (mode === "webcam" && streaming) {
      interval = setInterval(() => {
        captureWebcamFrame();
      }, 500);
    }
    return () => clearInterval(interval);
  }, [mode, streaming]);

  // =============================
  // IMAGE UPLOAD
  // =============================

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setPreview(URL.createObjectURL(file));
    setResult(null);

    const reader = new FileReader();
    reader.onloadend = async () => {
      await sendFrame(reader.result);
    };
    reader.readAsDataURL(file);
  };

  // =============================
  // SEND FRAME
  // =============================

  const sendFrame = async (imageBase64) => {
    setLoading(true);

    try {
      const response = await axios.post(
        `${API_URL}/api/stream-frame/`,
        { image: imageBase64 }
      );

      console.log("Backend response:", response.data);

      const safeData = {
        alignment_offset_pixels:
          response.data?.alignment_offset_pixels ?? 0,
        alignment_offset_mm:
          response.data?.alignment_offset_mm ?? 0,
        status: response.data?.status ?? "UNKNOWN",
      };

      setResult(safeData);
      drawOverlay(safeData, imageBase64);

    } catch (err) {
      console.error("Frame send error:", err);
    }

    setLoading(false);
  };

  // =============================
  // DRAW OVERLAY
  // =============================

  const drawOverlay = (data, src) => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");

    const img = new Image();
    img.src = src;

    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;

      ctx.drawImage(img, 0, 0);

      const centerX = canvas.width / 2;
      const detectedX =
        centerX + (data.alignment_offset_pixels || 0);

      // Ideal center
      ctx.strokeStyle = "lime";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(centerX, 0);
      ctx.lineTo(centerX, canvas.height);
      ctx.stroke();

      // Detected center
      ctx.strokeStyle = "red";
      ctx.beginPath();
      ctx.moveTo(detectedX, 0);
      ctx.lineTo(detectedX, canvas.height);
      ctx.stroke();
    };
  };

  // =============================
  // STATUS COLOR
  // =============================

  const getStatusColor = (status) => {
    if (status === "CRITICAL") return "red";
    if (status === "WARNING") return "orange";
    if (status === "OK") return "lime";
    return "gray";
  };

  // =============================
  // UI
  // =============================

  return (
    <div style={styles.container}>
      <h1>Conveyor Alignment Monitor</h1>

      <div style={styles.card}>
        <h3>Select Mode</h3>
        <button onClick={() => setMode("upload")} style={styles.button}>
          Upload Image
        </button>
        <button onClick={() => setMode("webcam")} style={styles.button}>
          Use Webcam
        </button>
      </div>

      {mode === "upload" && (
        <div style={styles.card}>
          <h3>Upload Image</h3>
          <input type="file" accept="image/*" onChange={handleFileChange} />
          {preview && (
            <img
              src={preview}
              alt="preview"
              style={{ maxWidth: "640px", marginTop: 10 }}
            />
          )}
        </div>
      )}

      {mode === "webcam" && (
        <div style={styles.card}>
          <h3>Live Webcam</h3>
          <video ref={videoRef} autoPlay style={{ width: "640px" }} />
          <div style={{ marginTop: 10 }}>
            {!streaming ? (
              <button onClick={startWebcam} style={styles.button}>
                Start Webcam
              </button>
            ) : (
              <button onClick={stopWebcam} style={styles.stopButton}>
                Stop Webcam
              </button>
            )}
          </div>
        </div>
      )}

      <div style={styles.card}>
        <canvas ref={canvasRef} style={{ maxWidth: "100%" }} />
        {loading && <p>Analyzing...</p>}

        {result && (
          <div>
            <p>Offset: {result.alignment_offset_mm} mm</p>
            <p style={{ color: getStatusColor(result.status) }}>
              Status: {result.status}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

const styles = {
  container: {
    backgroundColor: "#0f172a",
    minHeight: "100vh",
    padding: "40px",
    color: "white",
  },
  card: {
    backgroundColor: "#1e293b",
    padding: "20px",
    marginBottom: "20px",
    borderRadius: "10px",
  },
  button: {
    padding: "8px 16px",
    marginRight: 10,
    border: "none",
    borderRadius: 8,
    cursor: "pointer",
    backgroundColor: "#00ff99",
  },
  stopButton: {
    padding: "8px 16px",
    border: "none",
    borderRadius: 8,
    cursor: "pointer",
    backgroundColor: "#ff3b3b",
  },
};

export default App;