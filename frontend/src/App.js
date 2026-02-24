import React, { useRef, useState, useEffect } from "react";
import axios from "axios";

function App() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const fileInputRef = useRef(null);

  const [mode, setMode] = useState("upload");
  const [videoFile, setVideoFile] = useState(null);
  const [videoUrl, setVideoUrl] = useState(null);
  const [result, setResult] = useState(null);
  const [streaming, setStreaming] = useState(false);
  const [loading, setLoading] = useState(false);
  const [analysisHistory, setAnalysisHistory] = useState([]);
  const [isPlaying, setIsPlaying] = useState(false);

  const API_URL = "http://localhost:8000";

  // =============================
  // VIDEO FILE HANDLING
  // =============================

  const handleVideoChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (!file.type.startsWith('video/')) {
      alert('Please select a valid video file');
      return;
    }

    setVideoFile(file);
    const url = URL.createObjectURL(file);
    setVideoUrl(url);
    setResult(null);
    setAnalysisHistory([]);

    // Reset video element
    if (videoRef.current) {
      videoRef.current.src = url;
    }
  };

  // =============================
  // WEBCAM
  // =============================

  const startWebcam = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      videoRef.current.srcObject = stream;
      videoRef.current.play();
      setStreaming(true);
      setMode("webcam");
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
    setMode("upload");
  };

  // =============================
  // CAPTURE AND ANALYZE FRAME
  // =============================

  const captureAndAnalyzeFrame = async () => {
    if (!videoRef.current) return;

    const video = videoRef.current;

    // Create canvas to capture current frame
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext("2d");

    // For webcam or video element
    if (video.srcObject) {
      ctx.drawImage(video, 0, 0);
    } else {
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    }

    const imageBase64 = canvas.toDataURL("image/jpeg");
    await sendFrame(imageBase64, video.currentTime);
  };

  // =============================
  // IMAGE UPLOAD
  // =============================

  const handleImageChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onloadend = async () => {
      await sendFrame(reader.result, 0);
    };
    reader.readAsDataURL(file);
  };

  // =============================
  // SEND FRAME TO BACKEND
  // =============================

  const sendFrame = async (imageBase64, timestamp = 0) => {
    setLoading(true);

    try {
      const response = await axios.post(
        `${API_URL}/api/stream-frame/`,
        { image: imageBase64 }
      );

      console.log("Backend response:", response.data);

      const safeData = {
        alignment_offset_pixels: response.data?.alignment_offset_pixels ?? 0,
        alignment_offset_mm: response.data?.alignment_offset_mm ?? 0,
        status: response.data?.status ?? "UNKNOWN",
        timestamp: timestamp
      };

      setResult(safeData);

      // Add to history (keep last 20 items)
      setAnalysisHistory(prev => {
        const newHistory = [safeData, ...prev].slice(0, 20);
        return newHistory;
      });

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
      const detectedX = centerX + (data.alignment_offset_pixels || 0);

      // Draw semi-transparent background for text
      ctx.fillStyle = "rgba(0, 0, 0, 0.7)";
      ctx.fillRect(10, 10, 280, 80);

      // Ideal center (dashed line)
      ctx.strokeStyle = "white";
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 5]);
      ctx.beginPath();
      ctx.moveTo(centerX, 0);
      ctx.lineTo(centerX, canvas.height);
      ctx.stroke();

      // Detected center (solid line with color based on status)
      ctx.setLineDash([]);
      if (data.status === "CRITICAL") ctx.strokeStyle = "red";
      else if (data.status === "WARNING") ctx.strokeStyle = "orange";
      else ctx.strokeStyle = "lime";

      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.moveTo(detectedX, 0);
      ctx.lineTo(detectedX, canvas.height);
      ctx.stroke();

      // Draw text
      ctx.font = "bold 16px Arial";
      ctx.fillStyle = "white";
      ctx.fillText(`Offset: ${data.alignment_offset_mm} mm`, 20, 35);
      ctx.fillText(`Status: ${data.status}`, 20, 65);

      if (data.timestamp > 0) {
        ctx.fillText(`Time: ${data.timestamp.toFixed(2)}s`, 20, 95);
      }
    };
  };

  // =============================
  // VIDEO PLAYBACK CONTROL
  // =============================

  const handleVideoPlay = () => {
    setIsPlaying(true);
    startFrameCapture();
  };

  const handleVideoPause = () => {
    setIsPlaying(false);
  };

  const startFrameCapture = () => {
    if (!videoRef.current) return;

    const interval = setInterval(() => {
      if (videoRef.current && !videoRef.current.paused) {
        captureAndAnalyzeFrame();
      }
    }, 1000); // Capture every second

    return () => clearInterval(interval);
  };

  useEffect(() => {
    let interval;
    if (mode === "webcam" && streaming) {
      interval = setInterval(() => {
        captureAndAnalyzeFrame();
      }, 1000);
    } else if (mode === "video" && isPlaying && videoRef.current) {
      interval = setInterval(() => {
        if (!videoRef.current.paused) {
          captureAndAnalyzeFrame();
        }
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [mode, streaming, isPlaying]);

  // =============================
  // RESET
  // =============================

  const resetVideo = () => {
    if (videoUrl) {
      URL.revokeObjectURL(videoUrl);
    }
    setVideoFile(null);
    setVideoUrl(null);
    setResult(null);
    setAnalysisHistory([]);
    setIsPlaying(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // =============================
  // STATUS COLOR
  // =============================

  const getStatusColor = (status) => {
    if (status === "CRITICAL") return "#ff4444";
    if (status === "WARNING") return "#ffaa00";
    if (status === "OK") return "#00ff88";
    return "#888888";
  };

  // =============================
  // UI
  // =============================

  return (
    <div style={styles.container}>
      <h1 style={styles.title}>Conveyor Alignment Monitor</h1>

      {/* Mode Selection */}
      <div style={styles.card}>
        <h3>Select Input Mode</h3>
        <div style={styles.buttonGroup}>
          <button
            onClick={() => setMode("upload")}
            style={{...styles.button, backgroundColor: mode === "upload" ? "#00ff99" : "#4a5568"}}
          >
            Upload Image
          </button>
          <button
            onClick={() => setMode("video")}
            style={{...styles.button, backgroundColor: mode === "video" ? "#00ff99" : "#4a5568"}}
          >
            Upload Video
          </button>
          <button
            onClick={startWebcam}
            style={{...styles.button, backgroundColor: mode === "webcam" ? "#00ff99" : "#4a5568"}}
          >
            Use Webcam
          </button>
        </div>
      </div>

      {/* Upload Image Section */}
      {mode === "upload" && (
        <div style={styles.card}>
          <h3>Upload Image</h3>
          <input
            type="file"
            accept="image/*"
            onChange={handleImageChange}
            style={styles.fileInput}
          />
        </div>
      )}

      {/* Upload Video Section */}
      {mode === "video" && (
        <div style={styles.card}>
          <h3>Upload Video</h3>
          <input
            ref={fileInputRef}
            type="file"
            accept="video/*"
            onChange={handleVideoChange}
            style={styles.fileInput}
          />

          {videoFile && (
            <div style={styles.videoInfo}>
              <p>File: {videoFile.name}</p>
              <p>Size: {(videoFile.size / (1024 * 1024)).toFixed(2)} MB</p>
            </div>
          )}
        </div>
      )}

      {/* Webcam Section */}
      {mode === "webcam" && streaming && (
        <div style={styles.card}>
          <h3>Live Webcam</h3>
          <button onClick={stopWebcam} style={styles.stopButton}>
            Stop Webcam
          </button>
        </div>
      )}

      {/* Video/Webcam Display */}
      <div style={styles.card}>
        <div style={styles.videoContainer}>
          {(mode === "video" || mode === "upload") && videoUrl && (
            <video
              ref={videoRef}
              src={videoUrl}
              controls
              onPlay={handleVideoPlay}
              onPause={handleVideoPause}
              style={styles.video}
            />
          )}

          {mode === "webcam" && (
            <video ref={videoRef} autoPlay style={styles.video} />
          )}

          {!videoUrl && mode === "video" && !streaming && (
            <div style={styles.placeholder}>
              <p>Select a video file to begin</p>
            </div>
          )}

          {!streaming && mode === "webcam" && (
            <div style={styles.placeholder}>
              <p>Click "Use Webcam" to start</p>
            </div>
          )}
        </div>

        {/* Canvas for overlay */}
        <canvas ref={canvasRef} style={styles.canvas} />

        {loading && <p style={styles.loading}>Analyzing...</p>}
      </div>

      {/* Results Panel */}
      <div style={styles.resultsPanel}>
        <h3>Live Analysis</h3>

        {result && (
          <div style={styles.currentResult}>
            <div style={styles.metric}>
              <span>Offset:</span>
              <span style={{fontWeight: 'bold'}}>{result.alignment_offset_mm} mm</span>
            </div>
            <div style={styles.metric}>
              <span>Status:</span>
              <span style={{
                ...styles.statusBadge,
                backgroundColor: getStatusColor(result.status),
                color: result.status === "WARNING" ? "#000" : "#fff"
              }}>
                {result.status}
              </span>
            </div>
          </div>
        )}

        {/* History */}
        {analysisHistory.length > 0 && (
          <div style={styles.history}>
            <h4>Recent Measurements</h4>
            <div style={styles.historyList}>
              {analysisHistory.map((item, idx) => (
                <div key={idx} style={styles.historyItem}>
                  <span>{item.timestamp > 0 ? `${item.timestamp.toFixed(1)}s` : 'Frame'}</span>
                  <span>{item.alignment_offset_mm} mm</span>
                  <span style={{
                    ...styles.historyStatus,
                    backgroundColor: getStatusColor(item.status)
                  }}>
                    {item.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {videoFile && (
          <button onClick={resetVideo} style={styles.resetButton}>
            Clear Video
          </button>
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
    fontFamily: "Arial, sans-serif",
  },
  title: {
    textAlign: "center",
    marginBottom: "30px",
    color: "#00ff99",
  },
  card: {
    backgroundColor: "#1e293b",
    padding: "20px",
    marginBottom: "20px",
    borderRadius: "10px",
    boxShadow: "0 4px 6px rgba(0,0,0,0.3)",
  },
  buttonGroup: {
    display: "flex",
    gap: "10px",
    flexWrap: "wrap",
  },
  button: {
    padding: "10px 20px",
    border: "none",
    borderRadius: "8px",
    cursor: "pointer",
    fontWeight: "bold",
    color: "#0f172a",
    transition: "all 0.3s",
  },
  stopButton: {
    padding: "10px 20px",
    border: "none",
    borderRadius: "8px",
    cursor: "pointer",
    backgroundColor: "#ff4444",
    color: "white",
    fontWeight: "bold",
  },
  fileInput: {
    width: "100%",
    padding: "10px",
    backgroundColor: "#2d3748",
    color: "white",
    border: "1px solid #4a5568",
    borderRadius: "5px",
    cursor: "pointer",
  },
  videoInfo: {
    marginTop: "10px",
    padding: "10px",
    backgroundColor: "#2d3748",
    borderRadius: "5px",
  },
  videoContainer: {
    position: "relative",
    width: "100%",
    minHeight: "300px",
    backgroundColor: "#000",
    borderRadius: "10px",
    overflow: "hidden",
  },
  video: {
    width: "100%",
    display: "block",
  },
  canvas: {
    width: "100%",
    marginTop: "10px",
    border: "1px solid #4a5568",
    borderRadius: "5px",
  },
  placeholder: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    height: "300px",
    color: "#888",
  },
  loading: {
    textAlign: "center",
    color: "#00ff99",
    marginTop: "10px",
  },
  resultsPanel: {
    backgroundColor: "#1e293b",
    padding: "20px",
    borderRadius: "10px",
    marginTop: "20px",
  },
  currentResult: {
    backgroundColor: "#2d3748",
    padding: "15px",
    borderRadius: "8px",
    marginBottom: "20px",
  },
  metric: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "10px",
    fontSize: "16px",
  },
  statusBadge: {
    padding: "5px 15px",
    borderRadius: "20px",
    fontWeight: "bold",
  },
  history: {
    marginTop: "20px",
  },
  historyList: {
    maxHeight: "200px",
    overflowY: "auto",
  },
  historyItem: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "8px",
    backgroundColor: "#2d3748",
    marginBottom: "5px",
    borderRadius: "5px",
    fontSize: "14px",
  },
  historyStatus: {
    padding: "2px 8px",
    borderRadius: "12px",
    fontSize: "12px",
    fontWeight: "bold",
  },
  resetButton: {
    width: "100%",
    padding: "10px",
    marginTop: "20px",
    backgroundColor: "#4a5568",
    color: "white",
    border: "none",
    borderRadius: "5px",
    cursor: "pointer",
    fontWeight: "bold",
  },
};

export default App;