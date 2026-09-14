from flask import Blueprint, render_template

from app.services.analytics_service import analytics_data

analytics_bp = Blueprint("analytics", __name__, url_prefix="/analytics")


@analytics_bp.get("")
def index():
    return render_template("analytics/index.html", analytics=analytics_data())
