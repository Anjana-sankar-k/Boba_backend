from fastapi import FastAPI, HTTPException
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

# Allow React Native (Expo) dev and prod requests
origins = [
    "http://localhost:8081",   # Expo Go on local
    "http://localhost:19006",  # Expo web preview
    "http://localhost:3000",   # If testing on React web
    "*"  # TEMP: for development only — allow all
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

# Ensure geospatial index
users_collection.create_index([("location", "2dsphere")])

# ---------------- Models ----------------
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

# ---------------- Routes ----------------
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
        # Skip self
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
