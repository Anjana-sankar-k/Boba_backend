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
    allow_origins= "https://bobachat.streamlit.app/", 
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
    password: str
    latitude: float  # New field
    longitude: float  # New field

# ----------------- ROOT ROUTE -----------------
@app.get("/")
async def root():
    return {"message": "Boba API is live and ready to serve!"}

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
        "password": hashed_pw.decode('utf-8'),
        "location": {
            "type": "Point",
            "coordinates": [user.longitude, user.latitude]
        }
    }
    users_collection.insert_one(new_user)

    return {"message": "User registered successfully!"}

# ----------------- LOGIN -----------------
@app.post("/login")
async def login(user: User):
    existing_user = users_collection.find_one({"username": user.username})
    if not existing_user:
        raise HTTPException(status_code=401, detail="User not found")

    stored_password = existing_user["password"].encode('utf-8')
    if not bcrypt.checkpw(user.password.encode('utf-8'), stored_password):
        raise HTTPException(status_code=401, detail="Invalid password")

    return {"message": "Login successful!", "user_id": str(existing_user["_id"])}

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

    return dumps(list(nearby_users))  # Convert MongoDB cursor to JSON
