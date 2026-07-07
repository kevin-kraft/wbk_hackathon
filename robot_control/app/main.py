from fastapi import Depends, FastAPI

from app import env
from app.auth import require_token
from app.routers import commands, joint_states, robot_commands, robot_workflows

app = FastAPI(title="LARA5 Jetson Bridge")

# Shared-token auth on every router (no-op unless WBK_API_TOKEN is set); /health
# below stays open for monitoring.
_auth = [Depends(require_token)]
app.include_router(commands.router, dependencies=_auth)
app.include_router(joint_states.router, dependencies=_auth)
app.include_router(robot_commands.router, dependencies=_auth)
app.include_router(robot_workflows.router, dependencies=_auth)

@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn  # local import: the container starts via the `uvicorn` CLI, and
    # importing it at module scope makes `app.main` un-importable without uvicorn.

    print(f"Starting LARA5 API Server on {env.API_HOST}:{env.API_PORT}")

    uvicorn.run(
        app,
        host=env.API_HOST,
        port=env.API_PORT,
        log_level="info",
    )
