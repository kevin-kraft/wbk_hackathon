import uvicorn
from fastapi import FastAPI

from app import env 
from app.routers import commands, joint_states, robot_commands, robot_workflows

app = FastAPI(title="LARA5 Jetson Bridge")

app.include_router(commands.router)
app.include_router(joint_states.router)
app.include_router(robot_commands.router)
app.include_router(robot_workflows.router)

@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    print(f"Starting LARA5 API Server on {env.API_HOST}:{env.API_PORT}")

    uvicorn.run(
        app,
        host=env.API_HOST,
        port=env.API_PORT,
        log_level="info",
    )
