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
    role: str

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        message = Message(**data)
        room_code = message.roomCode
        username = message.username
        role = message.role

        # Check if the room document exists, otherwise create it
        room = await db.rooms.find_one({"roomCode": room_code})
        if not room:
            await db.rooms.insert_one({"roomCode": room_code, "online": [username], "sender": None, "replier": None, "messages": []})
        else:
            # Update the online field with the new username
            await db.rooms.update_one(
                {"roomCode": room_code},
                {"$addToSet": {"online": username}}
            )

            # Update the sender or replier field based on the user's role
            if role == "Sender":
                await db.rooms.update_one({"roomCode": room_code}, {"$set": {"sender": username}})
            elif role == "Replier":
                await db.rooms.update_one({"roomCode": room_code}, {"$set": {"replier": username}})

        # Retrieve the updated room document
        room = await db.rooms.find_one({"roomCode": room_code})

        # Send the existing messages to the client
        existing_messages = room.get("messages", [])
        await websocket.send_json({"type": "existingMessages", "messages": existing_messages})

        # Send the updated online users, sender, and replier information to all connected clients
        online_users = room.get("online", [])
        online_count = len(online_users)
        sender = room.get("sender", None)
        replier = room.get("replier", None)
        for connection in connections.values():
            await connection.send_json({"type": "userInfo", "onlineUsers": online_users, "onlineCount": online_count, "sender": sender, "replier": replier})

        # Store the connected WebSocket in the connections dictionary
        connections[websocket] = websocket

        while True:
            data = await websocket.receive_json()
            message = Message(**data)
            content = message.content
            username = message.username  # Add this line

            # Update the messages field with the new message
            if content:
                await db.rooms.update_one(
                    {"roomCode": room_code},
                    {"$push": {"messages": {"content": content, "username": username}}}  # Modify this line
                )

                # Send the new message to all connected clients
                for connection in connections.values():
                    await connection.send_json({"type": "message", "content": content, "username": username})  # Modify this line

    except WebSocketDisconnect:
        # Remove the disconnected WebSocket from the connections dictionary
        if websocket in connections:
            del connections[websocket]

        # Remove the disconnected user from the online field
        await db.rooms.update_one(
            {"roomCode": room_code},
            {"$pull": {"online": username}}
        )

        # Remove the user from the sender or replier field
        await db.rooms.update_one(
            {"roomCode": room_code},
            {"$set": {"sender": None if role == "Sender" else room.get("sender", None),
                      "replier": None if role == "Replier" else room.get("replier", None)}}
        )

        # Retrieve the updated room document
        room = await db.rooms.find_one({"roomCode": room_code})

        # Send the updated online users, sender, and replier information to all connected clients
        online_users = room.get("online", [])
        online_count = len(online_users)
        sender = room.get("sender", None)
        replier = room.get("replier", None)
        for connection in connections.values():
            await connection.send_json({"type": "userInfo", "onlineUsers": online_users, "onlineCount": online_count, "sender": sender, "replier": replier})

        await websocket.close()
        
# API endpoint for pinging to keep the server alive
@app.get("/ping")
async def ping():
    return {"message": "pong"}

@app.head("/ping_header")
async def ping_header():
    """
    Endpoint to check if the server is up and running.
    """
    return {"message": "pong"}

# Periodically ping the server to keep it alive (e.g., every 5 minutes)
async def periodic_ping():
    while True:
        await asyncio.sleep(150)  # 150 seconds = 2 minutes and 30 seconds
        await ping()

# Start the periodic ping task
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(periodic_ping())