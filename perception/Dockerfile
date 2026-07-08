# CUDA + torch base — torch/torchvision ship with the image at a matching CUDA
# version, which sidesteps the usual GPU-wheel pain for ultralytics / SAM / etc.
# Override for newer GPUs: Blackwell (sm_120) needs CUDA 12.8+/torch 2.7+, e.g.
#   --build-arg BASE_IMAGE=pytorch/pytorch:2.8.0-cuda12.8-cudnn9-devel
ARG BASE_IMAGE=pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime
FROM ${BASE_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PERCEPTION_DEVICE=cuda \
    WEIGHTS_DIR=/weights \
    HF_HOME=/root/.cache/huggingface

WORKDIR /app/perception

# System libs OpenCV / rendering need, plus git for pip-from-source model repos.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 git \
    && rm -rf /var/lib/apt/lists/*

# Install deps first for layer caching. `requirements.txt` is the consolidated
# list the image uses; per-service requirements.txt files are for future splits.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code.
COPY . .

# yolo :8001 · sam3 :8002 · locateanything :8003 · dds :8008
EXPOSE 8001 8002 8003 8008

CMD ["supervisord", "-c", "/app/perception/supervisord.conf"]
