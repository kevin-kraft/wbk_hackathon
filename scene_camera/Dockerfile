# Scene-camera capture service (CPU FastAPI). Single uvicorn process on :9002.
#
# The `zivid` backend needs the Zivid SDK + the physical camera, which live on
# the Jetson (ARM64). This image builds the CPU service and its mock/file
# backends; to run the real zivid backend, build/run this on the Jetson with the
# Zivid SDK installed and `pip install zivid`, pass the USB device through
# (--device / --privileged), and set SCENE_CAMERA_BACKEND=zivid. Natively running
# it in the Jetson's Zivid-enabled venv is often simpler than Docker for USB HW.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the package into /app/scene_camera so `scene_camera.app:app` imports cleanly.
COPY . /app/scene_camera

EXPOSE 9002
CMD ["uvicorn", "scene_camera.app:app", "--host", "0.0.0.0", "--port", "9002"]
