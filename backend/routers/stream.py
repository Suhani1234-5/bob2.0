import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# one list of open connections per PR
connections: dict[int, list[WebSocket]] = {}

@router.websocket("/ws/verification/{pr_id}/stream")
async def stream(ws: WebSocket, pr_id: int):
    await ws.accept()
    connections.setdefault(pr_id, []).append(ws)
    try:
        while True:
            await ws.receive_text()  # keeps the connection open
    except WebSocketDisconnect:
        connections[pr_id].remove(ws)

# any agent can call this to push an update to the frontend
async def broadcast(pr_id: int, message: dict):
    for ws in connections.get(pr_id, []):
        await ws.send_json(message)

# fake test trigger

@router.post("/api/debug/fake-run/{pr_id}")
async def fake_run(pr_id: int):
    agents = ["requirement", "investigator", "reproducer", "fixer", "adversarial", "regression"]
    for a in agents:
        await broadcast(pr_id, {"agent": a, "status": "running"})
        await asyncio.sleep(2)
        await broadcast(pr_id, {"agent": a, "status": "complete"})
    return {"done": True}