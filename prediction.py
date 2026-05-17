from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import get_db
from models import Patient, Vital
from auth import get_current_patient
from vitals import get_prediction

router = APIRouter(prefix="/prediction", tags=["Prediction"])


@router.get("/current")
def get_current_prediction(patient: Patient = Depends(get_current_patient), db: Session = Depends(get_db)):
    """Get the current prediction based on the latest vital and all history."""
    history_records = (
        db.query(Vital)
        .filter(Vital.patient_id == patient.patient_id)
        .order_by(Vital.timestamp)
        .all()
    )

    if not history_records:
        return {
            "vgi": 0,
            "risk_category": "Stable",
            "estimated_hours_to_deterioration": None,
            "explanation": [{"factor": "No vitals recorded", "value": "N/A", "impact": "low"}],
            "baseline": {},
            "timeline": [],
            "alert": False,
            "alert_message": None,
        }

    latest = history_records[-1]
    current = {
        "heart_rate": latest.heart_rate,
        "spo2": latest.spo2,
        "temperature": latest.temperature,
        "respiratory_rate": latest.respiratory_rate,
        "systolic_bp": latest.systolic_bp,
        "diastolic_bp": latest.diastolic_bp,
    }

    history = [
        {
            "heart_rate": v.heart_rate,
            "spo2": v.spo2,
            "temperature": v.temperature,
            "respiratory_rate": v.respiratory_rate,
            "systolic_bp": v.systolic_bp,
            "diastolic_bp": v.diastolic_bp,
        }
        for v in history_records[:-1]
    ]

    return get_prediction(current, history)
