# Robot-control (movement) bridge — CPU-only FastAPI service. Talks to the LARA5
# robot socket server (ROBOT_HOST:ROBOT_PORT) and the KIP pose API; no ML stack.
#
# Runs on :9000 to match the orchestrator's MOVEMENT_URL slot (contracts/movement_api.md).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    API_PORT=9000

WORKDIR /app/robot_control

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the service so `app.main:app` imports cleanly (the code uses `from app...`).
COPY . /app/robot_control

EXPOSE 9000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
