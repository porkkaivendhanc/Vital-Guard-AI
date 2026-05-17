from datetime import datetime, timezone, timedelta
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.sql import func
from database import Base

IST = timezone(timedelta(hours=5, minutes=30))


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(IST))


class Vital(Base):
    __tablename__ = "vitals"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String(50), ForeignKey("patients.patient_id"), nullable=False, index=True)
    heart_rate = Column(Float, nullable=False)
    spo2 = Column(Float, nullable=False)
    temperature = Column(Float, nullable=False)
    respiratory_rate = Column(Float, nullable=False)
    systolic_bp = Column(Float, nullable=False)
    diastolic_bp = Column(Float, nullable=False)
    vgi = Column(Float, nullable=True)
    risk_category = Column(String(50), nullable=True)
    estimated_hours_to_deterioration = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(IST))
