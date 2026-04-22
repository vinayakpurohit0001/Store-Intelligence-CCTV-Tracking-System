# 💜 Purplle Store Intelligence — AI Vision Platform
**Real-Time Retail Analytics, Cross-Camera Tracking, and Intelligence Dashboard**

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-0063B1?style=for-the-badge&logo=ai)](https://github.com/ultralytics/ultralytics)
[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)

## 📌 Project Overview
Purplle Store Intelligence is a production-grade AI platform that transforms raw CCTV footage into high-fidelity retail insights. By synchronizing multiple camera feeds, the system provides a holistic view of customer behavior, brand engagement, and operational efficiency.

### 🧠 Core Capabilities
- **Global Re-Identification (Re-ID)**: Syncs visitor IDs across multiple cameras (Entry, Floor, Billing) so a single customer is tracked as one unique entity throughout their journey.
- **Brand Zone Heatmaps**: Real-time traffic analysis for specific brand sections (e.g., Lakme, Faces Canada, The Face Shop).
- **Staff Filtering**: Automatically detects store employees via uniform color analysis and excludes them from customer metrics for 100% accurate conversion data.
- **Conversion Funnels**: Tracks the 4-stage journey from Store Entry → Zone Browsing → Billing Queue → Final Purchase.
- **Anomaly Detection**: Flags operational issues like long billing wait times or high abandonment rates.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Python 3.10+**
- **CCTV Footage**: Ensure your `.mp4` files are placed in `dataset/CCTV Footage/` (Named CAM_1, CAM_2, etc.)

### 2. Installation
```powershell
# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install AI and Backend dependencies
pip install -r requirements.txt
```

### 3. Execution (3 Simple Steps)

#### **Step A: Start the Intelligence API**
The API handles all data processing, Re-ID synchronization, and dashboard streaming.
```powershell
uvicorn app.main:app --port 8000
```

#### **Step B: Launch the Multi-Camera Visualizer**
This runs the AI pipeline on all 4 camera feeds simultaneously and displays the live grid.
```powershell
.\run_grid_visual.ps1
```

#### **Step C: View the Dashboard**
Simply open **`dashboard.html`** in any modern browser. 
> Access the live command center at: `http://localhost:8000/dashboard`

---

## 📂 System Architecture

### 🛡️ AI Pipeline (`/pipeline`)
- **Detection**: YOLOv8n optimized for retail environments.
- **Tracking**: ByteTrack for persistent ID retention within a single feed.
- **Re-ID**: MobileNetV3 feature extraction for cross-camera visitor matching.
- **Staff classification**: HSV-based torso analysis to identify uniforms.

### 🌐 Intelligence API (`/app`)
- **FastAPI Backend**: High-performance, asynchronous event ingestion.
- **Global Registry**: A centralized Re-ID store that prevents duplicate visitor counts across cameras.
- **SSE Streaming**: Pushes live metrics to the dashboard every 3 seconds without page refreshes.

### 📊 Real-World Data Layout
The system is pre-configured for the **Purplle Store Layout**:
- **CAM_1**: Tracks entry and "Minimalist" brand zone.
- **CAM_2**: Monitors "Fragrance" and high-traffic floor areas.
- **CAM_3**: Focused on "Lakme", "Faces Canada", and "The Face Shop".
- **CAM_5**: Dedicated to the Billing Counter and Queue depth analysis.

---

## 🛠️ Configuration
All store-specific logic (polygon coordinates for brand zones, camera resolutions, and store IDs) is managed via:
`dataset/store_layout.json`

## 🐳 Docker Support
For containerized deployment:
```bash
docker-compose up --build
```

---
**Developed for Purplle Retail Excellence.**
