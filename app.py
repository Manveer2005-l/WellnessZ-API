from flask import Flask, request, jsonify
import pandas as pd
import requests
import os

from wellnessz_runtime import predict_clients, generate_explanation
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ---- ENV ----
API_KEY = os.getenv("WELLNESSZ_API_KEY", "dev-key")

DATA_MODE = os.getenv("DATA_MODE", "NONE")  # NONE | REMOTE
CLIENT_API_BASE_URL = os.getenv("CLIENT_API_BASE_URL")
CLIENT_API_KEY = os.getenv("CLIENT_API_KEY")


# ---------- helpers ----------

def fetch_client_metrics(client_id: str) -> dict:
    """
    Fetch client metrics from external backend
    """
    if DATA_MODE != "REMOTE":
        raise RuntimeError("REMOTE data mode not enabled")

    if not CLIENT_API_BASE_URL:
        raise RuntimeError("CLIENT_API_BASE_URL not set")

    url = f"{CLIENT_API_BASE_URL}/clients/{client_id}"
    headers = {
        "Authorization": f"Bearer {CLIENT_API_KEY}",
        "Content-Type": "application/json"
    }

    resp = requests.get(url, headers=headers, timeout=10)

    if resp.status_code != 200:
        raise RuntimeError(f"Client fetch failed ({resp.status_code})")

    data = resp.json()

    # defaults if missing
    data.setdefault("age", 1)
    data.setdefault("sex", 1)

    return data


# ---------- routes ----------

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/predict", methods=["POST"])
def predict_manual():
    auth = request.headers.get("Authorization")
    if auth != f"Bearer {API_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(force=True)

    if "metrics" not in payload:
        return jsonify({"error": "metrics missing"}), 400

    metrics = payload["metrics"]
    metrics.setdefault("age", 1)
    metrics.setdefault("sex", 1)

    df = pd.DataFrame([metrics])
    df["client_id"] = payload.get("client_id", "MANUAL")

    df_out = predict_clients(df)
    row = df_out.iloc[0]

    return jsonify(_format_response(row))


@app.route("/predict/by-id", methods=["POST"])
def predict_by_id():
    auth = request.headers.get("Authorization")
    if auth != f"Bearer {API_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(force=True)
    client_id = payload.get("client_id")

    if not client_id:
        return jsonify({"error": "client_id missing"}), 400

    try:
        metrics = fetch_client_metrics(client_id)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    df = pd.DataFrame([metrics])
    df["client_id"] = client_id

    df_out = predict_clients(df)
    row = df_out.iloc[0]

    return jsonify(_format_response(row))


# ---------- formatter ----------

def _format_response(row):
    explanation = generate_explanation(row)

    return {
        "client_id": row.client_id,
        "triage": row.triage,
        "control_focus": row.control_focus,
        "health_distance": float(row.health_distance),
        "risks": {
            "diabetes": float(row.pred_diab),
            "blood_pressure": float(row.pred_bp),
            "lipids": float(row.pred_lip)
        },
        "explanation": explanation
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
