# Built ON TOP OF the FoundationPose GPU base image, which carries torch,
# nvdiffrast, pytorch3d and the FoundationPose repo (at /workspace/FoundationPose).
# Build that base first from ~/code/FoundationPose/docker/Dockerfile.blackwell:
#   docker build -t foundationpose:blackwell -f docker/Dockerfile.blackwell .
# (Retag for your GPU arch — the reference base targets Blackwell / sm_120.)
FROM foundationpose:blackwell

# The base image installs into /opt/venv.
RUN /opt/venv/bin/pip install --no-cache-dir \
        fastapi "uvicorn[standard]" pydantic opencv-python-headless

WORKDIR /svc
COPY shared /svc/shared
COPY foundationpose_svc /svc/foundationpose_svc

ENV PYTHONPATH=/svc \
    FP_REPO=/workspace/FoundationPose \
    FP_MESH_DIR=/meshes \
    PYOPENGL_PLATFORM=egl

EXPOSE 8004
CMD ["/opt/venv/bin/uvicorn", "foundationpose_svc.app:app", "--host", "0.0.0.0", "--port", "8004"]
