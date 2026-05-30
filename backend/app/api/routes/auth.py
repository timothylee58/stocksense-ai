from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db.user_models import UserModel, init_user_table
from app.core.security import hash_password, verify_password, create_token

router = APIRouter()

class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/auth/register")
def register(req: RegisterRequest):
    init_user_table()
    if UserModel.select().where(UserModel.username == req.username).exists():
        raise HTTPException(status_code=409, detail="Username already taken")
    user = UserModel.create(
        username=req.username,
        hashed_password=hash_password(req.password),
    )
    return {"id": user.id, "username": user.username}

@router.post("/auth/login")
def login(req: LoginRequest):
    try:
        user = UserModel.get(UserModel.username == req.username)
    except UserModel.DoesNotExist:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(user.id, user.username)
    return {"access_token": token, "token_type": "bearer"}
