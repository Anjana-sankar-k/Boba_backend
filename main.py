from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pydantic import BaseModel
import bcrypt
import os
from dotenv import load_dotenv
from bson import ObjectId

# Load environment variables
load_dotenv()

app = FastAPI()

origins = [
    "http://localhost:8081",
    "http://localhost:19006",
    "http://localhost:3000",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB connection
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI is not set in the environment variables!")

client = MongoClient(MONGO_URI)
db = client["boba_db"]
users_collection = db["users"]
connections_collection = db["connections"]

users_collection.create_index([("location", "2dsphere")])

# WebSocket manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        self.active_connections.pop(user_id, None)

    async def send_personal_message(self, message: str, user_id: str):
        websocket = self.active_connections.get(user_id)
        if websocket:
            await websocket.send_text(message)

    async def broadcast(self, message: str):
        for ws in self.active_connections.values():
            await ws.send_text(message)

manager = ConnectionManager()

# Models
class User(BaseModel):
    username: str
    gmail: str
    password: str
    bio: str
    interests: str
    latitude: float
    longitude: float

class LoginUser(BaseModel):
    username: str
    password: str

class ConnectRequest(BaseModel):
    from_user_id: str
    to_user_id: str
@app.get("/")
async def root():
    return {"message": "Boba API is live and ready to serve!"}

@app.get("/test")
async def test():
    return {"message": "Backend is working!"}

@app.post("/signup")
async def signup(user: User):
    existing_user = users_collection.find_one({"username": user.username})
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    hashed_pw = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt())

    new_user = {
        "username": user.username,
        "gmail": user.gmail,
        "password": hashed_pw.decode('utf-8'),
        "bio": user.bio,
        "interests": user.interests,
        "location": {
            "type": "Point",
            "coordinates": [user.longitude, user.latitude]
        },
        "longitude": user.longitude,
        "latitude": user.latitude
    }

    inserted_user = users_collection.insert_one(new_user)

    return {
        "message": "User registered successfully!",
        "_id": str(inserted_user.inserted_id),
        "username": user.username,
        "gmail": user.gmail,
        "bio": user.bio,
        "interests": user.interests,
        "longitude": user.longitude,
        "latitude": user.latitude
    }

@app.post("/login")
async def login(user: LoginUser):
    existing_user = users_collection.find_one({"username": user.username})
    if not existing_user:
        raise HTTPException(status_code=401, detail="User not found")

    stored_password = existing_user["password"].encode('utf-8')
    if not bcrypt.checkpw(user.password.encode('utf-8'), stored_password):
        raise HTTPException(status_code=401, detail="Invalid password")

    return {
        "message": "Login successful!",
        "user_id": str(existing_user["_id"]),
        "username": existing_user["username"],
        "gmail": existing_user["gmail"],
        "bio": existing_user["bio"],
        "interests": existing_user["interests"],
        "longitude": existing_user["longitude"],
        "latitude": existing_user["latitude"]
    }

@app.get("/matches/{user_id}")
async def get_nearby_users(user_id: str, max_distance: float = 5000):
    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if not user or "location" not in user:
        raise HTTPException(status_code=404, detail="User location not available")

    longitude, latitude = user["location"]["coordinates"]

    nearby_users = users_collection.find({
        "location": {
            "$near": {
                "$geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                "$maxDistance": max_distance
            }
        }
    })

    users_list = []
    for u in nearby_users:
        if str(u["_id"]) == user_id:
            continue
        users_list.append({
            "_id": str(u["_id"]),
            "username": u["username"],
            "gmail": u["gmail"],
            "bio": u["bio"],
            "interests": u["interests"],
            "longitude": u["longitude"],
            "latitude": u["latitude"]
        })

    return {"matches": users_list}

@app.get("/user/{user_id}")
async def get_user_details(user_id: str):
    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "_id": str(user["_id"]),
        "username": user["username"],
        "gmail": user["gmail"],
        "bio": user["bio"],
        "interests": user["interests"],
        "longitude": user["longitude"],
        "latitude": user["latitude"]
    }

@app.post("/connect")
async def send_connection_request(req: ConnectRequest):
    if req.from_user_id == req.to_user_id:
        raise HTTPException(status_code=400, detail="Cannot connect with yourself")

    existing = connections_collection.find_one({
        "from": req.from_user_id,
        "to": req.to_user_id
    })
    if not existing:
        connections_collection.insert_one({
            "from": req.from_user_id,
            "to": req.to_user_id
        })

    reverse = connections_collection.find_one({
        "from": req.to_user_id,
        "to": req.from_user_id
    })

    if reverse:
        await manager.send_personal_message("🎉 You matched with someone!", req.from_user_id)
        await manager.send_personal_message("🎉 You matched with someone!", req.to_user_id)
        return {
            "message": "It's a match! 🎉",
            "connected": True
        }
    else:
        await manager.send_personal_message("Someone sent you a connection request!", req.to_user_id)
        return {
            "message": "Connection request sent! Waiting for other user...",
            "connected": False
        }

@app.get("/connections/{user_id}")
async def get_mutual_connections(user_id: str):
    sent = connections_collection.find({"from": user_id})
    sent_ids = [c["to"] for c in sent]

    mutuals = []
    for to_id in sent_ids:
        reverse = connections_collection.find_one({"from": to_id, "to": user_id})
        if reverse:
            mutuals.append(to_id)

    return {"mutuals": mutuals}

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    try:
        print(f"🟢 Attempting connection for user: {user_id}")
        await manager.connect(user_id, websocket)
        print(f"✅ User {user_id} connected via WebSocket")

        while True:
            try:
                data = await websocket.receive_text()
                print(f"📩 Received from {user_id}: {data}")
                await manager.send_personal_message(f"You said: {data}", user_id)
            except Exception as e:
                print(f"⚠️ Error receiving/sending message for {user_id}: {e}")
                break

    except WebSocketDisconnect:
        print(f"🔌 User {user_id} disconnected")
        manager.disconnect(user_id)
    except Exception as e:
        print(f"❌ Unexpected WebSocket error for user {user_id}: {e}")
        manager.disconnect(user_id)

