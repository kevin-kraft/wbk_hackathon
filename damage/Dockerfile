# Damage inspection is a thin OpenRouter client — no GPU, no ML stack.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the package into /app/damage so `damage.app:app` imports cleanly.
COPY . /app/damage

EXPOSE 8006
CMD ["uvicorn", "damage.app:app", "--host", "0.0.0.0", "--port", "8006"]
