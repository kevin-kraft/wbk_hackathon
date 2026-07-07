# Built ON TOP OF the GigaPose GPU base image, which carries torch, xformers,
# panda3d, MegaPose and the GigaPose repo (at /workspace/GigaPose), pinned to
# numpy<2. Build that base first from ~/code/GigaPose/docker/Dockerfile.blackwell:
#   docker build -t gigapose:blackwell -f docker/Dockerfile.blackwell .
# (Retag for your GPU arch — the reference base targets Blackwell / sm_120.)
# Override for another GPU arch, e.g. RTX 5000 Ada (sm_89):
#   --build-arg BASE_IMAGE=gigapose:ada   (base built with TORCH_CUDA_ARCH_LIST=8.9)
#
# NOTE: this is a SEPARATE image from foundationpose:* on purpose — the two
# stacks disagree on numpy / xformers / panda3d and cannot co-exist.
ARG BASE_IMAGE=gigapose:blackwell
FROM ${BASE_IMAGE}

# Constrain numpy<2 in the SAME install: fastapi/opencv otherwise pull numpy 2.x,
# which breaks the base's numpy-1 ABI stack (pinocchio/MegaPose compiled for 1.x).
RUN /opt/venv/bin/pip install --no-cache-dir \
        fastapi "uvicorn[standard]" pydantic python-multipart opencv-python-headless "numpy<2"

WORKDIR /svc
COPY shared /svc/shared
COPY gigapose_svc /svc/gigapose_svc

ENV PYTHONPATH=/svc \
    GIGAPOSE_REPO=/workspace/GigaPose \
    GP_DATASET=kip2 \
    GP_REFINER_RENDERER=single \
    XFORMERS_DISABLED=1

EXPOSE 8005
CMD ["/opt/venv/bin/uvicorn", "gigapose_svc.app:app", "--host", "0.0.0.0", "--port", "8005"]
