from flask import Flask, request, jsonify
import pandas as pd
import os

from wellnessz_runtime import predict_clients, generate_explanation

# =========================================================
# App & Config
# =========================================================

app = Flask(__name__)

API_KEY = os.getenv("WELLNESSZ_API_KEY", "dev-key")

# Data mode:
# CSV  -> lookup client by ID from a dataset
# NONE -> backend sends metrics directly
DATA_MODE = os.getenv("DATA_MODE", "NONE")

CSV_PATH = os.getenv("CSV_PATH", "clients_full.csv")

_clients_df = None


# =========================================================
# Helpers
# =========================================================

def _load_clients_df():
    global _clients_df
    if _clients_df is None:
        if not os.path.exists(CSV_PATH):
            raise FileNotFoundError(f"CSV file not found: {CSV_PATH}")
        _clients_df = pd.read_csv(CSV_PATH)
        _clients_df["client_id"] = _clients_df["client_id"].astype(str)
    return _clients_df


def normalize_metrics(metrics: dict) -> dict:
    """
    Ensures required fields exist so the engine never breaks.
    Defaults are intentionally conservative.
    """
    metrics = metrics.copy()

    # Required by engine
    metrics.setdefault("age", 1)
    metrics.setdefault("sex", 1)

    return metrics


def get_client_metrics(client_id: str):
    """
    Dataset-agnostic client lookup.
    Can later be replaced with DB / API without touching endpoints.
    """
    if DATA_MODE != "CSV":
        return None

    df = _load_clients_df()
    row = df[df["client_id"] == str(client_id)]

    if row.empty:
        return None

    r = row.iloc[0]

    metrics = {
        "bmi": r.get("bmi"),
        "hm_visceral_fat": r.get("hm_visceral_fat"),
        "hm_muscle": r.get("hm_muscle"),
        "hm_rm": r.get("hm_rm"),
        "age": r.get("age", 1),
        "sex": r.get("sex", 1),
    }

    return normalize_metrics(metrics)


def authorize(req):
    auth = req.headers.get("Authorization")
    return auth == f"Bearer {API_KEY}"


def run_engine(metrics: dict, client_id: str):
    metrics = normalize_metrics(metrics)

    df = pd.DataFrame([metrics])
    df["client_id"] = client_id

    df_out = predict_clients(df)
    row = df_out.iloc[0]

    explanation = generate_explanation(row)

    return {
        "client_id": row.client_id,
        "triage": row.triage,
        "control_focus": row.control_focus,
        "health_distance": float(row.health_distance),
        "risks": {
            "diabetes": float(row.pred_diab),
            "blood_pressure": float(row.pred_bp),
            "lipids": float(row.pred_lip),
        },
        "explanation": explanation,
    }


# =========================================================
# Routes
# =========================================================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ---------------------------------------------------------
# 1️⃣ Manual metrics input (PRODUCTION RECOMMENDED)
# ---------------------------------------------------------
@app.route("/predict", methods=["POST"])
def predict_manual():

    if not authorize(request):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True)

    if "metrics" not in data:
        return jsonify({"error": "metrics missing"}), 400

    client_id = str(data.get("client_id", "UNKNOWN"))
    metrics = normalize_metrics(data["metrics"])

    return jsonify(run_engine(metrics, client_id))


# ---------------------------------------------------------
# 2️⃣ Client ID lookup from dataset (CSV / future DB)
# ---------------------------------------------------------
@app.route("/predict/by-id", methods=["POST"])
def predict_by_id():

    if not authorize(request):
        return jsonify({"error": "Unauthorized"}), 401

    if DATA_MODE != "CSV":
        return jsonify({"error": "Client lookup disabled"}), 400

    data = request.get_json(force=True)

    if "client_id" not in data:
        return jsonify({"error": "client_id missing"}), 400

    client_id = str(data["client_id"])

    metrics = get_client_metrics(client_id)

    if not metrics:
        return jsonify({"error": "client not found"}), 404

    return jsonify(run_engine(metrics, client_id))


# =========================================================
# Entrypoint
# =========================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
