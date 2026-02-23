#!/bin/bash

echo "🔧 Setting up YOLO service..."

# Create directories
mkdir -p models

# Test Python imports
python3 -c "
import sys
print(f'Python version: {sys.version}')
try:
    import torch
    print(f'✅ PyTorch version: {torch.__version__}')
    print(f'✅ CUDA available: {torch.cuda.is_available()}')
except ImportError:
    print('❌ PyTorch not installed')

try:
    import cv2
    print(f'✅ OpenCV version: {cv2.__version__}')
except ImportError:
    print('❌ OpenCV not installed')

try:
    from ultralytics import YOLO
    print('✅ Ultralytics YOLO imported')
except ImportError:
    print('❌ Ultralytics YOLO not installed')
"

echo "✅ YOLO service setup complete"