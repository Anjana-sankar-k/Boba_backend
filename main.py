from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pydantic import BaseModel
import bcrypt
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI()

# Enable CORS for Flutter requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this to specific domains for security in production
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

# User Model
class User(BaseModel):
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
    users_collection.insert_one({"username": user.username, "password": hashed_pw.decode('utf-8')})  # Convert bytes to string

    return {"message": "User registered successfully!"}

# ----------------- LOGIN -----------------
@app.post("/login")
async def login(user: User):
    existing_user = users_collection.find_one({"username": user.username})
    if not existing_user:
        raise HTTPException(status_code=401, detail="User not found")

    stored_password = existing_user["password"].encode('utf-8')  # Convert stored password back to bytes
    if not bcrypt.checkpw(user.password.encode('utf-8'), stored_password):  # ✅ Corrected: Use checkpw() instead of verify()
        raise HTTPException(status_code=401, detail="Invalid password")

    return {"message": "Login successful!"}
