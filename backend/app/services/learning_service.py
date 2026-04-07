"""
Learning Service
----------------
Phase 5 ML training pipeline. Trains a GradientBoostingRegressor on published
post engagement data and stores the resulting model artifacts in GCS.

Public API:
  - train_scoring_model(db)   — full train/evaluate/persist pipeline
  - get_active_model(db)      — fetch the currently-active TrainingRecord
  - load_model_from_gcs(path) — download (model, scaler) tuple from GCS

The model is trained automatically once 200 published posts exist, and can
also be triggered manually via the API.
"""
from __future__ import annotations

import io
import logging
import math
from datetime import datetime, timezone
from typing import Optional

import joblib
import numpy as np
import pytz
from google.cloud.firestore_v1.async_client import AsyncClient
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler

from app.config import get_settings
from app.core.firestore import COLLECTIONS, get_firestore_client
from app.models.learning import ModelAccuracyMetrics, TopFeature, TrainingRecord

logger = logging.getLogger("suas.services.learning")

_MANILA_TZ = pytz.timezone("Asia/Manila")
_ELIGIBLE_STATUSES = ["published", "metrics_synced"]
_MIN_TRAINING_SAMPLES = 200
_R2_THRESHOLD = 0.30

_FEATURE_NAMES = [
    "alignment_score",
    "urgency_score",
    "has_voice_statement",
    "hour_of_day",
    "day_of_week",
    "urgency_tier_hot",
    "urgency_tier_warm",
    "post_type_amplify",
]


# ─── Public API ───────────────────────────────────────────────────────────────


async def train_scoring_model(db: AsyncClient) -> Optional[TrainingRecord]:
    """
    Full ML training pipeline.

    1. Fetch published posts with engagement data from Firestore.
    2. Build feature matrix X and target vector y.
    3. Gate: require at least 200 samples.
    4. Cross-validate a GradientBoostingRegressor; gate on R² >= 0.30.
    5. Fit on full dataset, upload model + scaler PKLs to GCS.
    6. Mark previous active model as inactive.
    7. Write and return a new TrainingRecord.

    Returns None if training was skipped (too few samples or low R²).
    """
    # ── 1. Fetch training data ────────────────────────────────────────────────
    X_rows: list[list[float]] = []
    y_values: list[float] = []
    post_ids: list[str] = []

    query = (
        db.collection(COLLECTIONS["posts"])
        .where("status", "in", _ELIGIBLE_STATUSES)
    )

    async for doc in query.stream():
        data = doc.to_dict() or {}
        if "id" not in data:
            data["id"] = doc.id

        row = _extract_features(data)
        if row is None:
            continue

        features, target = row
        X_rows.append(features)
        y_values.append(target)
        post_ids.append(data["id"])

    n_samples = len(X_rows)

    # ── 4. Gate: minimum sample count ────────────────────────────────────────
    if n_samples < _MIN_TRAINING_SAMPLES:
        logger.info(
            "Not enough data (%d posts). Need %d+", n_samples, _MIN_TRAINING_SAMPLES
        )
        return None

    X = np.array(X_rows, dtype=float)
    y = np.array(y_values, dtype=float)

    # ── 5a. Cross-validate ────────────────────────────────────────────────────
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = GradientBoostingRegressor(
        n_estimators=100, max_depth=4, random_state=42
    )
    cv_scores = cross_val_score(model, X_scaled, y, cv=5, scoring="r2")
    r2 = float(np.mean(cv_scores))

    # ── 6. Gate: R² threshold ─────────────────────────────────────────────────
    if r2 < _R2_THRESHOLD:
        logger.info(
            "Model R²=%.3f below threshold %.2f — not saving", r2, _R2_THRESHOLD
        )
        return None

    # ── 7a. Fit on full dataset ───────────────────────────────────────────────
    model.fit(X_scaled, y)

    # ── 9. MAE on training set (approximate) ─────────────────────────────────
    mae = float(np.mean(np.abs(model.predict(X_scaled) - y)))

    # ── 8. Feature importances ────────────────────────────────────────────────
    top_features = sorted(
        [
            TopFeature(name=name, importance=float(imp))
            for name, imp in zip(_FEATURE_NAMES, model.feature_importances_)
        ],
        key=lambda f: f.importance,
        reverse=True,
    )

    # ── 7b. Determine model version ───────────────────────────────────────────
    existing_count = 0
    async for _ in db.collection(COLLECTIONS["model_training"]).stream():
        existing_count += 1
    version = f"v{existing_count + 1}"

    # ── 7c. Serialize and upload to GCS ──────────────────────────────────────
    model_gcs_path = f"models/scorer_{version}.pkl"
    scaler_gcs_path = f"models/scaler_{version}.pkl"

    await _upload_pkl_to_gcs(model, model_gcs_path)
    await _upload_pkl_to_gcs(scaler, scaler_gcs_path)

    # ── 7d. Deactivate all previous training records ──────────────────────────
    batch = db.batch()
    async for doc in db.collection(COLLECTIONS["model_training"]).stream():
        ref = db.collection(COLLECTIONS["model_training"]).document(doc.id)
        batch.update(ref, {"is_active": False})
    await batch.commit()

    # ── 7e. Create and save new TrainingRecord ────────────────────────────────
    record = TrainingRecord(
        posts_in_training_set=n_samples,
        model_version=version,
        accuracy_metrics=ModelAccuracyMetrics(
            r_squared=r2,
            mae=mae,
            training_set_size=n_samples,
        ),
        top_features=top_features,
        gcs_path=model_gcs_path,
        is_active=True,
    )

    await (
        db.collection(COLLECTIONS["model_training"])
        .document(record.id)
        .set(record.to_firestore())
    )

    logger.info(
        "Model %s trained — R²=%.3f, MAE=%.4f, posts=%d",
        version, r2, mae, n_samples,
    )
    return record


async def get_active_model(db: AsyncClient) -> Optional[TrainingRecord]:
    """Return the currently-active TrainingRecord, or None if none exists."""
    query = (
        db.collection(COLLECTIONS["model_training"])
        .where("is_active", "==", True)
        .limit(1)
    )
    async for doc in query.stream():
        data = doc.to_dict() or {}
        try:
            return TrainingRecord(**data)
        except Exception as exc:
            logger.error("Failed to parse active TrainingRecord %s: %s", doc.id, exc)
            return None
    return None


async def load_model_from_gcs(
    gcs_path: str,
) -> Optional[tuple[object, object]]:
    """
    Download scorer and scaler PKL files from GCS.

    The scaler path is derived by replacing 'scorer_' with 'scaler_' in
    gcs_path (e.g. 'models/scorer_v1.pkl' → 'models/scaler_v1.pkl').

    Returns (model, scaler) on success, or None on any failure.
    """
    import asyncio

    scaler_path = gcs_path.replace("scorer_", "scaler_")

    try:
        model_bytes, scaler_bytes = await asyncio.gather(
            asyncio.to_thread(_download_gcs_bytes, gcs_path),
            asyncio.to_thread(_download_gcs_bytes, scaler_path),
        )
        model = joblib.load(io.BytesIO(model_bytes))
        scaler = joblib.load(io.BytesIO(scaler_bytes))
        logger.info("Loaded model from GCS: %s", gcs_path)
        return model, scaler
    except Exception as exc:
        logger.error("Failed to load model from GCS (%s): %s", gcs_path, exc)
        return None


# ─── Private helpers ──────────────────────────────────────────────────────────


def _extract_features(post: dict) -> Optional[tuple[list[float], float]]:
    """
    Extract (feature_vector, target) from a Firestore post document.

    Returns None if the post lacks required fields or has zero engagement.
    """
    scoring = post.get("scoring") or {}
    metrics = post.get("metrics") or {}

    # Must have alignment_score
    if scoring.get("alignment_score") is None:
        return None

    likes = int(metrics.get("likes") or 0)
    comments = int(metrics.get("comments") or 0)
    shares = int(metrics.get("shares") or 0)

    # Must have non-zero engagement
    if likes + comments + shares == 0:
        return None

    alignment_score = _safe_float(scoring.get("alignment_score"), 0.5)
    urgency_score = _safe_float(scoring.get("urgency_score"), 0.3)

    post_type = post.get("post_type") or ""
    urgency = post.get("urgency") or ""

    has_voice_statement = 1.0 if post_type == "amplify" else 0.0
    urgency_tier_hot = 1.0 if urgency == "hot" else 0.0
    urgency_tier_warm = 1.0 if urgency == "warm" else 0.0
    post_type_amplify = 1.0 if post_type == "amplify" else 0.0

    # Time features from publishing.published_at in Asia/Manila
    manila_dt = _parse_published_at_manila(post)
    hour_of_day = float(manila_dt.hour) if manila_dt is not None else 12.0
    day_of_week = float(manila_dt.weekday()) if manila_dt is not None else 0.0

    features = [
        alignment_score,
        urgency_score,
        has_voice_statement,
        hour_of_day,
        day_of_week,
        urgency_tier_hot,
        urgency_tier_warm,
        post_type_amplify,
    ]

    # Target: log1p of weighted engagement
    target = math.log1p(likes + 2 * comments + 3 * shares)

    return features, target


def _safe_float(value: object, default: float) -> float:
    """Clamp value to [0.0, 1.0]; return default on failure."""
    try:
        return max(0.0, min(1.0, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _parse_published_at_manila(post: dict):
    """Return a Manila-localised datetime from publishing.published_at, or None."""
    from datetime import datetime as _dt

    raw = (post.get("publishing") or {}).get("published_at")
    if raw is None:
        return None
    try:
        if isinstance(raw, _dt):
            dt = raw
        else:
            dt = _dt.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        return dt.astimezone(_MANILA_TZ)
    except (ValueError, TypeError, OverflowError):
        return None


async def _upload_pkl_to_gcs(obj: object, gcs_path: str) -> None:
    """Serialize obj with joblib and upload to GCS at gcs_path."""
    import asyncio

    settings = get_settings()

    buf = io.BytesIO()
    joblib.dump(obj, buf)
    buf.seek(0)
    pkl_bytes = buf.read()

    await asyncio.to_thread(_write_gcs_bytes, settings.gcs_bucket_name, gcs_path, pkl_bytes)
    logger.debug("Uploaded %s (%d bytes) to GCS bucket %s", gcs_path, len(pkl_bytes), settings.gcs_bucket_name)


def _write_gcs_bytes(bucket_name: str, blob_path: str, data: bytes) -> None:
    """Synchronous GCS upload — intended to be called via asyncio.to_thread."""
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.upload_from_string(data, content_type="application/octet-stream")


def _download_gcs_bytes(gcs_path: str) -> bytes:
    """Synchronous GCS download — intended to be called via asyncio.to_thread."""
    from google.cloud import storage

    settings = get_settings()
    client = storage.Client()
    bucket = client.bucket(settings.gcs_bucket_name)
    blob = bucket.blob(gcs_path)
    return blob.download_as_bytes()
