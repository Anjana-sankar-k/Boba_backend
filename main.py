from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pydantic import BaseModel
import bcrypt
import os
from dotenv import load_dotenv
from bson import ObjectId
from bson.json_util import dumps

# Load environment variables
load_dotenv()

app = FastAPI()

# Enable CORS for Streamlit requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://bobachat.streamlit.app"],  # Fixed (list, not string)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB Connection
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI is not set in the environment variables!")

client = MongoClient(MONGO_URI)
db = client["boba_db"]
users_collection = db["users"]

# Ensure GeoSpatial Indexing for location-based queries
users_collection.create_index([("location", "2dsphere")])

# User Model
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

# ----------------- ROOT ROUTE -----------------
@app.get("/")
async def root():
    return {"message": "Boba API is live and ready to serve!"}

# ----------------- TEST ROUTE -----------------
@app.get("/test")
async def test():
    return {"message": "Backend is working!"}

# ----------------- SIGNUP -----------------
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

# ----------------- LOGIN -----------------
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

# ----------------- GET PROXIMITY-BASED MATCHES -----------------
@app.get("/matches/{user_id}")
async def get_nearby_users(user_id: str, max_distance: float = 5000):  # Default max 5km
    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if not user or "location" not in user:
        raise HTTPException(status_code=404, detail="User location not available")

    longitude, latitude = user["location"]["coordinates"]

    nearby_users = users_collection.find({
        "location": {
            "$near": {
                "$geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                "$maxDistance": max_distance  # Max distance in meters
            }
        }
    })

    users_list = []
    for u in nearby_users:
        users_list.append({
            "_id": str(u["_id"]),
            "username": u["username"],
            "gmail": u["gmail"],
            "bio": u["bio"],
            "interests": u["interests"],
            "longitude": u["longitude"],
            "latitude": u["latitude"]
        })

    return {"matches": users_list}  # Return list of nearby users
