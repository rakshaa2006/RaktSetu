"""Uvicorn entry point:  uvicorn app.main:app --reload --port 8000"""
from app.factory import create_app

app = create_app()
