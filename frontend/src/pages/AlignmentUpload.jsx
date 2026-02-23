import React, { useState, useRef } from "react";
import axios from "axios";

const API_URL = process.env.REACT_APP_API_URL;

export default function AlignmentUpload() {
  const [image, setImage] = useState(null);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const canvasRef = useRef(null);

  const handleImageChange = (e) => {
    const file = e.target.files[0];
    setImage(file);
    setPreview(URL.createObjectURL(file));
    setResult(null);
  };

  const handleUpload = async () => {
    const formData = new FormData();
    formData.append("image", image);

    const response = await axios.post(`${API_URL}/alignment/`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });

    setResult(response.data);
    drawOverlay(response.data);
  };

  const drawOverlay = (data) => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");

    const img = new Image();
    img.src = preview;

    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      ctx.drawImage(img, 0, 0);

      const centerX = img.width / 2;
      const detectedX = centerX + data.offset_pixels;

      // Ideal center line (green)
      ctx.strokeStyle = "green";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(centerX, 0);
      ctx.lineTo(centerX, img.height);
      ctx.stroke();

      // Detected belt center (red)
      ctx.strokeStyle = "red";
      ctx.beginPath();
      ctx.moveTo(detectedX, 0);
      ctx.lineTo(detectedX, img.height);
      ctx.stroke();
    };
  };

  return (
    <div style={{ padding: 30 }}>
      <h2>Conveyor Belt Alignment Check</h2>

      <input type="file" accept="image/*" onChange={handleImageChange} />

      {preview && (
        <div style={{ marginTop: 20 }}>
          <button onClick={handleUpload}>Analyze Alignment</button>
          <canvas ref={canvasRef} style={{ marginTop: 20 }} />
        </div>
      )}

      {result && (
        <div style={{ marginTop: 20 }}>
          <h3>Result:</h3>
          <p>Offset: {result.offset_mm} mm</p>
          <p>Status: {result.status}</p>
        </div>
      )}
    </div>
  );
}