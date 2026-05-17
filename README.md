# VITAL-GUARD AI — Predictive Clinical Deterioration Monitoring Platform

A full-stack healthcare monitoring platform that predicts early clinical deterioration 6–12 hours before a critical event.

## Features
- **ML-Powered Predictions** — Random Forest + Gradient Boosting models (99.5% accuracy)
- **Risk Fusion Engine** — Combines snapshot + trend analysis
- **Explainable AI** — Shows why predictions were made
- **Patient Baseline Analysis** — Personalized risk detection
- **Risk Timeline Forecast** — Projects risk 12 hours ahead
- **Alert System** — Triggers when VitalGuard Index ≥ 80%

## Tech Stack
- **Frontend**: React + Vite + TailwindCSS + Chart.js
- **Backend**: Python FastAPI
- **ML**: scikit-learn (Random Forest, Gradient Boosting)
- **Database**: SQLite (PostgreSQL-compatible schema included)

## Run Locally
```bash
cd backend
pip install -r requirements.txt
python main.py
```
Open http://localhost:8000

## Project Structure
```
backend/
├── main.py              # FastAPI app
├── auth.py              # JWT authentication
├── vitals.py            # Vitals API + prediction
├── prediction.py        # Prediction endpoint
├── database.py          # DB connection
├── models.py            # ORM models
├── ml-service/          # ML models + training
├── database/            # SQL schema
├── static/              # Built React frontend
└── requirements.txt
frontend/                # React source code
```
