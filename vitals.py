import sys
import os
import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import get_db
from models import Patient, Vital
from auth import get_current_patient

# Add ml-service to path for predictions
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "ml-service"))

router = APIRouter(prefix="/vitals", tags=["Vitals"])


# ── Schemas ──────────────────────────────────────────────
class VitalInput(BaseModel):
    heart_rate: float
    spo2: float
    temperature: float
    respiratory_rate: float
    systolic_bp: float
    diastolic_bp: float


class VitalResponse(BaseModel):
    id: int
    heart_rate: float
    spo2: float
    temperature: float
    respiratory_rate: float
    systolic_bp: float
    diastolic_bp: float
    vgi: Optional[float] = None
    risk_category: Optional[str] = None
    estimated_hours_to_deterioration: Optional[float] = None
    timestamp: str

    class Config:
        from_attributes = True


class VitalAddResponse(BaseModel):
    vital: VitalResponse
    prediction: dict


# ── Helpers ──────────────────────────────────────────────
def get_prediction(current_vitals: dict, history: list) -> dict:
    """Get prediction from ML service, with rule-based fallback."""
    try:
        from predict_service import predict_risk
        result = predict_risk(current_vitals, history)
        if result is not None:
            return result
    except Exception as e:
        pass
    # Fallback: rule-based prediction if ML models not available
    return rule_based_prediction(current_vitals, history)


def rule_based_prediction(vitals: dict, history: list) -> dict:
    """Medical-grade fallback risk calculation with physiological pattern matching.
    Uses the same clinical classification logic as the ML pathway.
    """
    # Import shared classification engine
    try:
        from predict_service import (
            classify_by_physiology, get_clinical_reasoning, estimate_hours,
            _get_abnormalities, compute_baseline as ml_compute_baseline,
            NORMAL_RANGES
        )
        use_ml_classifier = True
    except ImportError:
        use_ml_classifier = False

    risk = 0.0
    hr = vitals["heart_rate"]
    spo2 = vitals["spo2"]
    temp = vitals["temperature"]
    rr = vitals["respiratory_rate"]
    sbp = vitals["systolic_bp"]
    dbp = vitals.get("diastolic_bp", 80)

    # ── VGI Score Calculation (unchanged — this is the severity score) ──
    # Heart rate risk
    if hr > 130 or hr < 45:
        risk += 30
    elif hr > 110 or hr < 55:
        risk += 18
    elif hr > 100 or hr < 60:
        risk += 8

    # SpO2 risk
    if spo2 < 85:
        risk += 35
    elif spo2 < 90:
        risk += 25
    elif spo2 < 93:
        risk += 15
    elif spo2 < 95:
        risk += 8

    # Temperature risk
    if temp > 40.0 or temp < 34.5:
        risk += 25
    elif temp > 39.0 or temp < 35.5:
        risk += 15
    elif temp > 38.3 or temp < 36.0:
        risk += 8

    # Respiratory rate risk
    if rr > 35 or rr < 8:
        risk += 30
    elif rr > 28 or rr < 10:
        risk += 18
    elif rr > 22 or rr < 12:
        risk += 8

    # Blood pressure risk (both systolic and diastolic)
    if sbp < 70 or sbp > 200:
        risk += 25
    elif sbp < 85 or sbp > 180:
        risk += 15
    elif sbp < 95 or sbp > 160:
        risk += 8

    if dbp < 45 or dbp > 120:
        risk += 15
    elif dbp < 55 or dbp > 100:
        risk += 8

    # Trend analysis from history
    trend_risk = 0.0
    if len(history) >= 3:
        recent = history[-3:]
        hr_trend = recent[-1]["heart_rate"] - recent[0]["heart_rate"]
        spo2_trend = recent[-1]["spo2"] - recent[0]["spo2"]
        rr_trend = recent[-1]["respiratory_rate"] - recent[0]["respiratory_rate"]
        sbp_trend = recent[-1]["systolic_bp"] - recent[0]["systolic_bp"]

        if hr_trend > 15:
            trend_risk += 10
        if spo2_trend < -3:
            trend_risk += 15
        if rr_trend > 5:
            trend_risk += 10
        if sbp_trend < -15:
            trend_risk += 10

    # Baseline analysis
    baseline_deviation_risk = 0.0
    if len(history) >= 5:
        avg_hr = sum(h["heart_rate"] for h in history) / len(history)
        avg_spo2 = sum(h["spo2"] for h in history) / len(history)
        avg_sbp = sum(h["systolic_bp"] for h in history) / len(history)
        hr_dev = abs(vitals["heart_rate"] - avg_hr)
        spo2_dev = avg_spo2 - vitals["spo2"]
        sbp_dev = avg_sbp - vitals["systolic_bp"]
        if hr_dev > 30:
            baseline_deviation_risk += 10
        if spo2_dev > 5:
            baseline_deviation_risk += 10
        if sbp_dev > 20:
            baseline_deviation_risk += 8

    vgi = min(100, max(0, risk * 0.55 + trend_risk * 0.25 + baseline_deviation_risk * 0.20))

    # ── MEDICAL-GRADE CLASSIFICATION ──
    # Use physiological pattern matching instead of score thresholds
    if use_ml_classifier:
        category = classify_by_physiology(vitals, vgi, history)
        reasoning = get_clinical_reasoning(vitals, category)
        hours = estimate_hours(vgi, category)
    else:
        # Inline fallback if predict_service not available
        category, reasoning, hours = _inline_classify(vitals, vgi, hr, spo2, temp, rr, sbp, dbp)

    # Explanation with clinical reasoning
    factors = _build_explanation_factors(vitals, hr, spo2, temp, rr, sbp, dbp)

    # Baseline data
    baseline = {}
    if len(history) >= 5:
        baseline = {
            "heart_rate": round(sum(h["heart_rate"] for h in history) / len(history), 1),
            "spo2": round(sum(h["spo2"] for h in history) / len(history), 1),
            "temperature": round(sum(h["temperature"] for h in history) / len(history), 1),
            "respiratory_rate": round(sum(h["respiratory_rate"] for h in history) / len(history), 1),
            "systolic_bp": round(sum(h["systolic_bp"] for h in history) / len(history), 1),
            "diastolic_bp": round(sum(h.get("diastolic_bp", 80) for h in history) / len(history), 1),
        }

    # Timeline forecast
    timeline = []
    for h in [0, 2, 4, 6, 8, 10, 12]:
        projected = min(100, vgi + h * (vgi * 0.03))
        timeline.append({"hours": h, "risk": round(projected, 1)})

    alert = vgi >= 70 or category in ("Critical Deterioration", "Hemodynamic Shock", "Multi-Organ Risk")

    return {
        "vgi": round(vgi, 1),
        "risk_category": category,
        "clinical_reasoning": reasoning,
        "estimated_hours_to_deterioration": hours,
        "explanation": factors,
        "baseline": baseline,
        "timeline": timeline,
        "alert": alert,
        "alert_message": f"⚠️ {category}: {reasoning} Estimated deterioration in {hours} hours." if alert else None,
    }


def _inline_classify(vitals, vgi, hr, spo2, temp, rr, sbp, dbp):
    """Inline physiological classification when predict_service is unavailable."""
    # Shock check
    if sbp < 80 and hr > 110:
        cat = "Hemodynamic Shock"
        reason = f"SBP {sbp} mmHg with compensatory tachycardia (HR {hr} bpm) indicates circulatory collapse."
        hours = round(max(0.5, 1.5 - (vgi / 100)), 1)
        return cat, reason, hours

    # Critical
    has_critical = (hr > 150 or hr < 40 or spo2 < 88 or rr > 35 or rr < 8 or temp > 40 or sbp > 200 or sbp < 70)
    if has_critical and vgi >= 70:
        cat = "Critical Deterioration"
        reason = "Critical vital sign derangements with high deterioration index."
        hours = round(max(0.5, 2 - (vgi / 100)), 1)
        return cat, reason, hours

    # Multi-organ
    systems = 0
    if hr > 100 or hr < 60: systems += 1
    if spo2 < 95 or rr > 20: systems += 1
    if temp > 38.3 or temp < 36: systems += 1
    if sbp < 90 or sbp > 160 or dbp < 60 or dbp > 100: systems += 1
    if systems >= 3:
        cat = "Multi-Organ Risk"
        reason = f"Abnormalities across {systems} organ systems."
        hours = round(max(1, 6 - vgi * 0.05), 1)
        return cat, reason, hours

    # Sepsis / SIRS
    temp_abnormal = temp > 38.3 or temp < 36.0
    sirs_count = sum([temp_abnormal, hr > 90, rr > 20, spo2 < 94])
    if temp_abnormal and sirs_count >= 2:
        cat = "Sepsis / SIRS"
        reason = f"Temp {temp}°C with HR {hr} bpm, RR {rr}/min meets ≥2 SIRS criteria."
        hours = round(max(2, 10 - vgi * 0.08), 1)
        return cat, reason, hours

    # Cardiac
    hr_abnormal = hr > 100 or hr < 50
    bp_abnormal = sbp < 90 or dbp < 60 or sbp > 180 or dbp > 100
    if hr_abnormal and bp_abnormal:
        cat = "Cardiac Risk"
        reason = f"HR {hr} bpm with BP {sbp}/{dbp} mmHg indicates cardiac compromise."
        hours = round(max(2, 8 - vgi * 0.06), 1)
        return cat, reason, hours

    # Respiratory
    if spo2 < 92 or (spo2 < 95 and rr > 24) or rr > 28:
        cat = "Respiratory Failure"
        reason = f"SpO₂ {spo2}% with RR {rr}/min indicates respiratory failure."
        hours = round(max(1.5, 7 - vgi * 0.05), 1)
        return cat, reason, hours

    # Hypertensive
    if sbp > 180 or dbp > 120:
        cat = "Hypertensive Crisis"
        reason = f"BP {sbp}/{dbp} mmHg is severely elevated."
        hours = round(max(2, 6 - vgi * 0.04), 1)
        return cat, reason, hours

    # Mild abnormality
    has_any = (hr > 100 or hr < 60 or spo2 < 95 or temp > 38.3 or temp < 36
               or rr > 20 or rr < 12 or sbp < 90 or sbp > 140 or dbp < 60 or dbp > 90)
    if has_any:
        cat = "Mild Abnormality"
        reason = "Minor vital sign deviation detected, no syndrome pattern."
        hours = round(max(8, 24 - vgi * 0.2), 1)
        return cat, reason, hours

    return "Stable", "All vital signs within normal ranges.", round(48 - vgi * 0.3, 1)


def _build_explanation_factors(vitals, hr, spo2, temp, rr, sbp, dbp):
    """Build clinically-meaningful explanation factors."""
    factors = []

    clinical_notes = {
        "hr_high": "Tachycardia — may indicate cardiac stress, hypovolemia, or sepsis",
        "hr_low": "Bradycardia — may indicate heart block or increased vagal tone",
        "spo2_low": "Hypoxemia — impaired oxygen delivery, consider pneumonia, PE, or ARDS",
        "temp_high": "Fever — may indicate infection or inflammatory process",
        "temp_low": "Hypothermia — may indicate sepsis or exposure",
        "rr_high": "Tachypnea — may indicate respiratory distress or metabolic acidosis",
        "sbp_low": "Hypotension — may indicate shock or cardiac failure",
        "sbp_high": "Hypertension — risk of stroke and end-organ damage",
        "dbp_high": "Diastolic hypertension — increased peripheral resistance",
        "dbp_low": "Diastolic hypotension — may indicate vasodilation",
    }

    if hr > 100:
        severity = "critical" if hr > 130 else "moderate"
        factors.append({"factor": "Heart Rate Elevated", "value": f"{hr} bpm",
                        "impact": "high" if hr > 130 else "medium",
                        "severity": severity, "clinical_note": clinical_notes["hr_high"]})
    elif hr < 60:
        severity = "critical" if hr < 45 else "moderate"
        factors.append({"factor": "Heart Rate Low", "value": f"{hr} bpm",
                        "impact": "high" if hr < 45 else "medium",
                        "severity": severity, "clinical_note": clinical_notes["hr_low"]})

    if spo2 < 95:
        severity = "critical" if spo2 < 88 else "moderate"
        factors.append({"factor": "SpO₂ Below Normal", "value": f"{spo2}%",
                        "impact": "high" if spo2 < 90 else "medium",
                        "severity": severity, "clinical_note": clinical_notes["spo2_low"]})

    if temp > 38.3:
        severity = "critical" if temp > 40 else "moderate"
        factors.append({"factor": "Temperature Elevated", "value": f"{temp}°C",
                        "impact": "high" if temp > 39.5 else "medium",
                        "severity": severity, "clinical_note": clinical_notes["temp_high"]})
    elif temp < 36.0:
        severity = "critical" if temp < 35 else "moderate"
        factors.append({"factor": "Temperature Low", "value": f"{temp}°C",
                        "impact": "high" if temp < 35 else "medium",
                        "severity": severity, "clinical_note": clinical_notes["temp_low"]})

    if rr > 22:
        severity = "critical" if rr > 35 else "moderate"
        factors.append({"factor": "Respiratory Rate Elevated", "value": f"{rr}/min",
                        "impact": "high" if rr > 30 else "medium",
                        "severity": severity, "clinical_note": clinical_notes["rr_high"]})

    if sbp < 90:
        severity = "critical" if sbp < 70 else "moderate"
        factors.append({"factor": "Systolic BP Low", "value": f"{sbp} mmHg",
                        "impact": "high" if sbp < 80 else "medium",
                        "severity": severity, "clinical_note": clinical_notes["sbp_low"]})
    elif sbp > 160:
        severity = "critical" if sbp > 200 else "moderate"
        factors.append({"factor": "Systolic BP Elevated", "value": f"{sbp} mmHg",
                        "impact": "high" if sbp > 180 else "medium",
                        "severity": severity, "clinical_note": clinical_notes["sbp_high"]})

    if dbp > 100:
        factors.append({"factor": "Diastolic BP Elevated", "value": f"{dbp} mmHg",
                        "impact": "high" if dbp > 120 else "medium",
                        "severity": "critical" if dbp > 120 else "moderate",
                        "clinical_note": clinical_notes["dbp_high"]})
    elif dbp < 55:
        factors.append({"factor": "Diastolic BP Low", "value": f"{dbp} mmHg",
                        "impact": "high" if dbp < 45 else "medium",
                        "severity": "critical" if dbp < 45 else "moderate",
                        "clinical_note": clinical_notes["dbp_low"]})

    if not factors:
        factors.append({"factor": "All Vitals Within Range", "value": "Normal",
                        "impact": "low", "severity": "normal"})

    return factors


# ── Routes ───────────────────────────────────────────────
@router.post("/add", response_model=VitalAddResponse)
def add_vital(vital_input: VitalInput, patient: Patient = Depends(get_current_patient), db: Session = Depends(get_db)):
    # Get patient history
    history_records = (
        db.query(Vital)
        .filter(Vital.patient_id == patient.patient_id)
        .order_by(Vital.timestamp)
        .all()
    )

    history = [
        {
            "heart_rate": v.heart_rate,
            "spo2": v.spo2,
            "temperature": v.temperature,
            "respiratory_rate": v.respiratory_rate,
            "systolic_bp": v.systolic_bp,
            "diastolic_bp": v.diastolic_bp,
        }
        for v in history_records
    ]

    current = vital_input.model_dump()
    prediction = get_prediction(current, history)

    # Save vital with prediction
    vital = Vital(
        patient_id=patient.patient_id,
        heart_rate=vital_input.heart_rate,
        spo2=vital_input.spo2,
        temperature=vital_input.temperature,
        respiratory_rate=vital_input.respiratory_rate,
        systolic_bp=vital_input.systolic_bp,
        diastolic_bp=vital_input.diastolic_bp,
        vgi=prediction["vgi"],
        risk_category=prediction["risk_category"],
        estimated_hours_to_deterioration=prediction["estimated_hours_to_deterioration"],
    )
    db.add(vital)
    db.commit()
    db.refresh(vital)

    return VitalAddResponse(
        vital=VitalResponse(
            id=vital.id,
            heart_rate=vital.heart_rate,
            spo2=vital.spo2,
            temperature=vital.temperature,
            respiratory_rate=vital.respiratory_rate,
            systolic_bp=vital.systolic_bp,
            diastolic_bp=vital.diastolic_bp,
            vgi=vital.vgi,
            risk_category=vital.risk_category,
            estimated_hours_to_deterioration=vital.estimated_hours_to_deterioration,
            timestamp=vital.timestamp.isoformat() if vital.timestamp else "",
        ),
        prediction=prediction,
    )


@router.get("/history", response_model=List[VitalResponse])
def get_history(patient: Patient = Depends(get_current_patient), db: Session = Depends(get_db)):
    records = (
        db.query(Vital)
        .filter(Vital.patient_id == patient.patient_id)
        .order_by(desc(Vital.timestamp))
        .all()
    )
    return [
        VitalResponse(
            id=v.id,
            heart_rate=v.heart_rate,
            spo2=v.spo2,
            temperature=v.temperature,
            respiratory_rate=v.respiratory_rate,
            systolic_bp=v.systolic_bp,
            diastolic_bp=v.diastolic_bp,
            vgi=v.vgi,
            risk_category=v.risk_category,
            estimated_hours_to_deterioration=v.estimated_hours_to_deterioration,
            timestamp=v.timestamp.isoformat() if v.timestamp else "",
        )
        for v in records
    ]
