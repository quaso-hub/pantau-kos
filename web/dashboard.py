"""
web/dashboard.py  (v3.2)
Flask Blueprint: web dashboard untuk monitoring listing kos.
Routes:
  GET /dashboard                       → halaman utama SPA (filter + sort, SSR initial)
  GET /dashboard/api/listings          → JSON endpoint (realtime polling by frontend)
  GET /dashboard/<listing_id>          → halaman detail 1 listing
"""
import logging
from flask import Blueprint, render_template, request, jsonify

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


def _build_stats(listings: list[dict]) -> dict:
    """Hitung stat cards dari list listing."""
    total = len(listings)
    avg_score = (
        round(sum(l.get("score", 0) for l in listings) / total, 1)
        if total > 0 else 0
    )
    surveyed = sum(1 for l in listings if l.get("status") == "survey")
    return {"total": total, "avg_score": avg_score, "surveyed": surveyed}


@dashboard_bp.route("/", methods=["GET"])
def index():
    """Halaman utama dashboard — SPA shell dengan SSR initial data."""
    filters = {
        "price_min":  request.args.get("price_min", type=int),
        "price_max":  request.args.get("price_max", type=int),
        "dist_max":   request.args.get("dist_max", type=float),
        "area":       request.args.get("area", ""),
        "status":     request.args.get("status", ""),
    }
    sort_by  = request.args.get("sort", "score")
    sort_dir = request.args.get("dir",  "desc")

    listings = _get_listings(filters, sort_by, sort_dir)
    stats    = _build_stats(listings)

    return render_template(
        "index.html",
        listings=listings,
        filters=filters,
        sort_by=sort_by,
        sort_dir=sort_dir,
        stats=stats,
    )


@dashboard_bp.route("/api/listings", methods=["GET"])
def api_listings():
    """
    JSON API untuk realtime polling dari frontend SPA.
    Response: { listings: [...], stats: { total, avg_score, surveyed } }
    """
    filters = {
        "price_min":  request.args.get("price_min", type=int),
        "price_max":  request.args.get("price_max", type=int),
        "dist_max":   request.args.get("dist_max",  type=float),
        "area":       request.args.get("area",       ""),
        "status":     request.args.get("status",     ""),
    }
    sort_by  = request.args.get("sort", "score")
    sort_dir = request.args.get("dir",  "desc")

    listings = _get_listings(filters, sort_by, sort_dir)
    stats    = _build_stats(listings)

    return jsonify({"listings": listings, "stats": stats})


@dashboard_bp.route("/<listing_id>", methods=["GET"])
def detail(listing_id: str):
    """Halaman detail satu listing."""
    # Stub: ambil dari Firestore
    listing = {"id": listing_id}
    return render_template("detail.html", listing=listing)

