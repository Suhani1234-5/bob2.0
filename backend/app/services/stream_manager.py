from collections import defaultdict
from typing import Dict, List
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = defaultdict(list)

    async def connect(self, pr_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[pr_id].append(websocket)

    def disconnect(self, pr_id: int, websocket: WebSocket):
        if websocket in self.active_connections[pr_id]:
            self.active_connections[pr_id].remove(websocket)

    async def broadcast(self, pr_id: int, message: dict):
        for connection in list(self.active_connections[pr_id]):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(pr_id, connection)

stream_manager = ConnectionManager()

