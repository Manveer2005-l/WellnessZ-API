from flask import Flask, request, jsonify
import pandas as pd
from wellnessz_runtime import predict_clients, generate_explanation

app = Flask(__name__)

# ---------- Endpoint 1: Analyze CSV ----------
@app.route("/analyze", methods=["POST"])
def analyze_clients():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    df = pd.read_csv(file)

    results = predict_clients(df)
    return results.to_json(orient="records")


# ---------- Endpoint 2: Explain one client ----------
@app.route("/explain", methods=["POST"])
def explain_client():
    data = request.json
    df = pd.DataFrame([data])

    df = predict_clients(df)
    row = df.iloc[0]

    explanation = generate_explanation(row)

    return jsonify({
        "client_id": row.get("client_id", None),
        "triage": row.triage,
        "control_focus": row.control_focus,
        "health_distance": float(row.health_distance),
        "risks": {
            "diabetes": float(row.pred_diab),
            "blood_pressure": float(row.pred_bp),
            "lipids": float(row.pred_lip)
        },
        "explanation": explanation
    })
if __name__ == "__main__":
    app.run(debug=True)
#curl.exe -X POST http://127.0.0.1:5000/analyze -F "file=@clients.csv"