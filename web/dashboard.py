"""
web/dashboard.py  (v3.1)
Flask Blueprint: web dashboard untuk monitoring listing kos.
Routes:
  GET /dashboard                  → tabel semua listing (filter + sort)
  GET /dashboard/<listing_id>     → halaman detail 1 listing
"""
import logging
from flask import Blueprint, render_template, request

log = logging.getLogger("god-eye.dashboard")

dashboard_bp = Blueprint(
    "dashboard",
    __name__,
    url_prefix="/dashboard",
    template_folder="templates",
)


def _get_listings(filters: dict, sort_by: str, sort_dir: str) -> list[dict]:
    """
    Stub: ambil listing dari Firestore dengan filter + sort.
    TODO: implementasi penuh dengan AsyncClient + run_async.
    """
    return []


@dashboard_bp.route("/", methods=["GET"])
def index():
    """Halaman utama dashboard — tabel listing dengan filter."""
    # Filter params dari query string
    filters = {
        "price_min":  request.args.get("price_min", type=int),
        "price_max":  request.args.get("price_max", type=int),
        "dist_max":   request.args.get("dist_max", type=float),
        "area":       request.args.get("area", ""),
        "status":     request.args.get("status", ""),   # pending/survey/skip
    }
    sort_by  = request.args.get("sort", "score")        # score/date/price/distance
    sort_dir = request.args.get("dir", "desc")          # asc/desc

    listings = _get_listings(filters, sort_by, sort_dir)

    stats = {
        "total":    len(listings),
        "avg_score": round(sum(l.get("score", 0) for l in listings) / len(listings), 1) if listings else 0,
        "surveyed": sum(1 for l in listings if l.get("status") == "survey"),
    }

    return render_template(
        "index.html",
        listings=listings,
        filters=filters,
        sort_by=sort_by,
        sort_dir=sort_dir,
        stats=stats,
    )


@dashboard_bp.route("/<listing_id>", methods=["GET"])
def detail(listing_id: str):
    """Halaman detail satu listing."""
    # Stub: ambil dari Firestore
    listing = {"id": listing_id}
    return render_template("detail.html", listing=listing)
