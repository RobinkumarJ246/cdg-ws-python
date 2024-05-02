import asyncio
import motor.motor_asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional

app = FastAPI()
# MongoDB connection
client = motor.motor_asyncio.AsyncIOMotorClient("mongodb+srv://admin4321:iceberginflorida@cluster0.7nzmtv3.mongodb.net/?retryWrites=true&w=majority")
db = client.chatdatagen

# WebSocket connections
connections = {}

class Message(BaseModel):
    roomCode: str
    content: Optional[str] = None
    username: str

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        message = Message(**data)
        room_code = message.roomCode
        username = message.username

        # Check if the room document exists, otherwise create it
        room = await db.rooms.find_one({"roomCode": room_code})
        if not room:
            await db.rooms.insert_one({"roomCode": room_code, "online": [username], "messages": []})
        else:
            # Update the online field with the new username
            await db.rooms.update_one(
                {"roomCode": room_code},
                {"$addToSet": {"online": username}}
            )

        # Send the updated online users list to all connected clients
        online_users = room.get("online", [])
        for connection in connections.values():
            await connection.send_json({"type": "onlineUsers", "onlineUsers": online_users})

        while True:
            data = await websocket.receive_json()
            message = Message(**data)
            content = message.content

            # Update the messages field with the new message
            if content:
                await db.rooms.update_one(
                    {"roomCode": room_code},
                    {"$push": {"messages": content}}
                )

                # Send the new message to all connected clients
                for connection in connections.values():
                    await connection.send_json({"type": "message", "content": content})

    except WebSocketDisconnect:
        # Remove the disconnected user from the online field
        await db.rooms.update_one(
            {"roomCode": room_code},
            {"$pull": {"online": username}}
        )

        # Send the updated online users list to all connected clients
        online_users = (await db.rooms.find_one({"roomCode": room_code})).get("online", [])
        for connection in connections.values():
            await connection.send_json({"type": "onlineUsers", "onlineUsers": online_users})

        await websocket.close()