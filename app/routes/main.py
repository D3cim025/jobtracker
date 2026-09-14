from flask import Blueprint, jsonify, render_template

from app.services.dashboard_service import dashboard_data

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def home():
    return render_template("home.html", dashboard=dashboard_data())


@main_bp.get("/health")
def health():
    return jsonify(service="jobtracker", status="healthy"), 200
