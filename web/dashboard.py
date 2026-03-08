"""
web/dashboard.py  (v3.3)
Flask Blueprint: web dashboard untuk monitoring listing kos.
Routes:
  GET /dashboard                       → halaman utama (filter + sort, SSR initial)
  GET /dashboard/api/listings          → JSON endpoint (realtime polling by frontend)
  GET /dashboard/<listing_id>          → halaman detail 1 listing
"""
import asyncio
import logging
from flask import Blueprint, render_template, request, jsonify, current_app

log = logging.getLogger("god-eye.dashboard")

dashboard_bp = Blueprint(
    "dashboard",
    __name__,
    url_prefix="/dashboard",
    template_folder="templates",
)


def _get_container():
    """Ambil Container dari Flask app context (di-inject oleh main.py)."""
    return current_app.config.get("CONTAINER")


def _run_async(coro):
    """
    Jalankan coroutine dari Flask (sync) thread menggunakan PTB event loop.
    Fallback ke asyncio.run() jika loop belum ada.
    """
    try:
        from main import _ptb_loop
        if _ptb_loop and _ptb_loop.is_running():
            import concurrent.futures
            future = asyncio.run_coroutine_threadsafe(coro, _ptb_loop)
            return future.result(timeout=10.0)
    except Exception:
        pass
    # Fallback
    try:
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _get_listings(filters: dict, sort_by: str, sort_dir: str) -> list[dict]:
    """Ambil listing dari Firestore dengan filter + sort."""
    container = _get_container()
    if not container:
        return []
    try:
        raw = _run_async(container.listing_repo.get_recent(limit=50))
        if not raw:
            return []

        results = list(raw)

        # Apply filters
        if filters.get("price_min"):
            results = [l for l in results if (l.get("price_value") or 0) >= filters["price_min"]]
        if filters.get("price_max"):
            results = [l for l in results if (l.get("price_value") or 0) <= filters["price_max"]]
        if filters.get("dist_max"):
            results = [l for l in results if l.get("distance_km") is not None and l["distance_km"] <= filters["dist_max"]]
        if filters.get("area"):
            area_q = filters["area"].lower()
            results = [l for l in results if area_q in (l.get("location") or "").lower()]
        if filters.get("status"):
            results = [l for l in results if l.get("status") == filters["status"]]

        # Sort
        reverse = (sort_dir == "desc")
        key_map = {
            "score":       lambda l: l.get("score") or 0,
            "price":       lambda l: l.get("price_value") or 0,
            "distance_km": lambda l: l.get("distance_km") or 999,
            "timestamp":   lambda l: l.get("timestamp") or "",
        }
        sort_key = key_map.get(sort_by, key_map["score"])
        results.sort(key=sort_key, reverse=reverse)
        
        # Normalize field names untuk template compatibility
        for item in results:
            item.setdefault("id", item.get("listing_id"))
            item.setdefault("price", item.get("price_value"))
            item.setdefault("area", item.get("location"))
        
        return results
    except Exception as exc:
        log.warning("_get_listings error: %s", exc)
        return []


def _build_stats(listings: list[dict]) -> dict:
    """Hitung stat cards dari list listing."""
    total = len(listings)
    scored = [l.get("score") for l in listings if l.get("score") is not None]
    avg_score = round(sum(scored) / len(scored), 1) if scored else 0
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
    """JSON API untuk realtime polling dari frontend SPA."""
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
    """Halaman detail satu listing — ambil dari Firestore."""
    container = _get_container()
    listing = None
    if container:
        try:
            listing = _run_async(container.listing_repo.get(listing_id))
        except Exception as exc:
            log.warning("detail() Firestore error: %s", exc)

    if not listing:
        listing = {"id": listing_id}
    else:
        # Normalise field names sehingga template bisa pakai .price, .area, dll.
        listing.setdefault("id", listing.get("listing_id", listing_id))
        listing.setdefault("price", listing.get("price_value"))
        listing.setdefault("area", listing.get("location"))

    return render_template("detail.html", listing=listing)


@dashboard_bp.route("/api/delete/<listing_id>", methods=["POST", "DELETE"])
def api_delete_listing(listing_id: str):
    """
    Hard-delete listing dari Firestore.
    Response: {"ok": true/false, "deleted_id": "..."}
    """
    container = _get_container()
    if not container:
        return jsonify({"ok": False, "error": "Container not available"}), 503
    
    try:
        _run_async(container.listing_repo.delete(listing_id))
        log.info("Listing %s deleted via dashboard", listing_id)
        return jsonify({"ok": True, "deleted_id": listing_id})
    except Exception as exc:
        log.error("Delete failed for %s: %s", listing_id, exc)
        return jsonify({"ok": False, "error": str(exc)}), 500

