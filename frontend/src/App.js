import React, { useState, useEffect } from 'react';
import axios from 'axios';

function App() {
  const [apiStatus, setApiStatus] = useState('Checking...');
  const [detections, setDetections] = useState([]);

  useEffect(() => {
    // Check API health
    axios.get('/api/health')
      .then(response => {
        setApiStatus('Connected');
      })
      .catch(error => {
        setApiStatus('Disconnected');
      });
  }, []);

  return (
    <div style={{ padding: '20px' }}>
      <h1>Conveyor Belt Monitoring System</h1>
      <div>
        <h2>System Status</h2>
        <p>API Status: {apiStatus}</p>
      </div>
      <div>
        <h2>Live Detection Feed</h2>
        <p>Waiting for video feed...</p>
      </div>
    </div>
  );
}

export default App;