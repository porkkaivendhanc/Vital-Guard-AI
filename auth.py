from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Patient

router = APIRouter(prefix="/auth", tags=["Authentication"])

SECRET_KEY = "vitalguard-secret-key-change-in-production-2024"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    pwd_bytes = password.encode("utf-8")
    hashed_bytes = hashed.encode("utf-8")
    return bcrypt.checkpw(pwd_bytes, hashed_bytes)


# ── Schemas ──────────────────────────────────────────────
class RegisterRequest(BaseModel):
    patient_id: str
    password: str


class LoginRequest(BaseModel):
    patient_id: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    patient_id: str


# ── Helpers ──────────────────────────────────────────────
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_patient(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        patient_id: str = payload.get("sub")
        if patient_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if patient is None:
        raise credentials_exception
    return patient


# ── Routes ───────────────────────────────────────────────
@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(Patient).filter(Patient.patient_id == req.patient_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Patient ID already registered")

    hashed = hash_password(req.password)
    patient = Patient(patient_id=req.patient_id, password_hash=hashed)
    db.add(patient)
    db.commit()
    db.refresh(patient)

    token = create_access_token(data={"sub": patient.patient_id})
    return TokenResponse(access_token=token, token_type="bearer", patient_id=patient.patient_id)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.patient_id == req.patient_id).first()
    if not patient or not verify_password(req.password, patient.password_hash):
        raise HTTPException(status_code=401, detail="Invalid Patient ID or password")

    token = create_access_token(data={"sub": patient.patient_id})
    return TokenResponse(access_token=token, token_type="bearer", patient_id=patient.patient_id)
