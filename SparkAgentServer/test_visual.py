import sys
from pathlib import Path

# Add the SparkAgentServer dir to sys.path so services can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from services.visual import _INSIGHTFACE_READY, _YOLO_READY
    print("Visual module imported successfully!")
    print(f"InsightFace Ready: {_INSIGHTFACE_READY}")
    print(f"YOLO Ready: {_YOLO_READY}")
except Exception as e:
    print(f"Failed to load visual module: {e}")
