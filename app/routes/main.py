from flask import Blueprint, jsonify, render_template

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def home():
    return render_template("home.html")


@main_bp.get("/health")
def health():
    return jsonify(service="jobtracker", status="healthy"), 200

