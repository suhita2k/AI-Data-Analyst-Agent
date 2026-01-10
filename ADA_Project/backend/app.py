import io
import os
import time
import uuid
import math
from typing import Dict, Any

from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    flash,
    send_file,
)
from flask_cors import CORS
from flask_login import (
    login_user,
    logout_user,
    login_required,
    current_user,
)
from werkzeug.utils import secure_filename

from config import Config
from models import db
from models.user import User
from services import bcrypt, login_manager
from services.analysis import load_dataset, profile_dataset, summarize_dataset
from services.charting import figure_to_json, build_figure_from_spec, fallback_spec
from services.llm import generate_chart_spec_and_insight
from services.report import build_html_report
from services.auth import register_user, authenticate_user

# ---------------------------------------------------------
# Basic setup
# ---------------------------------------------------------

load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.from_object(Config)

# Ensure folders exist
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs("instance", exist_ok=True)

# Init extensions
db.init_app(app)
bcrypt.init_app(app)
login_manager.init_app(app)

# CORS for API routes
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Upload / dataset settings
ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}
MAX_FILE_MB = Config.MAX_FILE_MB
KEEP_UPLOAD_MINUTES = int(os.getenv("KEEP_UPLOAD_MINUTES", "60"))

# In-memory datasets: { id: { path, df, meta, created_at, history } }
DATASETS: Dict[str, Dict[str, Any]] = {}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def clean_for_json(obj):
    """
    Recursively replace NaN / inf with None so that JSON is valid
    and can be parsed by JavaScript (JSON.parse doesn't allow NaN).
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_for_json(v) for v in obj]
    return obj


# Create DB tables once at startup
with app.app_context():
    db.create_all()


# ---------------------------------------------------------
# Auth routes
# ---------------------------------------------------------

@app.route("/", methods=["GET"])
def root():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        confirm = request.form.get("confirm_password", "").strip()

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")

        try:
            register_user(email, password)
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))
        except ValueError as e:
            flash(str(e), "danger")
        except Exception:
            flash("Registration failed. Please try again.", "danger")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        user = authenticate_user(email, password)
        if user:
            login_user(user)
            flash("Logged in successfully.", "success")
            next_url = request.args.get("next")
            return redirect(next_url or url_for("dashboard"))
        else:
            flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ---------------------------------------------------------
# Dashboard page
# ---------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


# ---------------------------------------------------------
# API: upload dataset
# ---------------------------------------------------------

@app.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    if not allowed_file(file.filename):
        return (
            jsonify(
                {
                    "error": f"Unsupported type. "
                    f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
                }
            ),
            400,
        )

    filename = secure_filename(file.filename)
    dataset_id = str(uuid.uuid4())
    saved_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{dataset_id}_{filename}")
    file.save(saved_path)

    # Load & profile dataset
    try:
        df = load_dataset(saved_path)
        meta = profile_dataset(df)
        summary = summarize_dataset(df)
        meta["summary"] = summary

        DATASETS[dataset_id] = {
            "path": saved_path,
            "df": df,
            "meta": meta,
            "created_at": time.time(),
            "history": [],
        }
    except Exception as e:
        return jsonify({"error": f"Failed to read file: {str(e)}"}), 400

    # Clean NaN/inf before returning JSON
    return jsonify({"dataset_id": dataset_id, "meta": clean_for_json(meta)})


# ---------------------------------------------------------
# API: dataset schema
# ---------------------------------------------------------

@app.route("/api/datasets/<dataset_id>/schema", methods=["GET"])
@login_required
def api_schema(dataset_id: str):
    item = DATASETS.get(dataset_id)
    if not item:
        return jsonify({"error": "Dataset not found"}), 404
    return jsonify(
        {"dataset_id": dataset_id, "meta": clean_for_json(item["meta"])}
    )


# ---------------------------------------------------------
# API: ask question
# ---------------------------------------------------------

@app.route("/api/ask", methods=["POST"])
@login_required
def api_ask():
    body = request.get_json(silent=True) or {}
    dataset_id = body.get("dataset_id")
    question = (body.get("question") or "").strip()

    if not dataset_id or not question:
        return jsonify({"error": "dataset_id and question are required"}), 400

    item = DATASETS.get(dataset_id)
    if not item:
        return jsonify({"error": "Dataset not found"}), 404

    df = item["df"]
    meta = item["meta"]

    # Ask LLM
    try:
        spec = generate_chart_spec_and_insight(question, meta, df_sample=df.head(50))
        llm_error = None
    except Exception as e:
        spec = None
        llm_error = str(e)

    if not spec or not spec.get("chart"):
        spec = fallback_spec(question, meta)

    # Build chart
    try:
        fig, data_preview, agg_preview = build_figure_from_spec(df, spec["chart"])
        fig_json = figure_to_json(fig)
    except Exception as e:
        # Clean data preview if exists
        dp = (
            clean_for_json(data_preview.to_dict(orient="records"))
            if "data_preview" in locals()
            else []
        )
        return (
            jsonify(
                {
                    "answer": spec.get(
                        "insight",
                        "I generated an insight but couldn’t build a chart.",
                    ),
                    "chart_error": str(e),
                    "suggested_questions": spec.get("suggested_questions", []),
                    "data_preview": dp,
                }
            ),
            200,
        )

    # Save history
    item["history"].append(
        {
            "question": question,
            "insight": spec.get("insight", ""),
            "chart_spec": spec.get("chart", {}),
            "timestamp": time.time(),
        }
    )

    data_preview_clean = clean_for_json(
        data_preview.to_dict(orient="records")
    )
    agg_preview_clean = (
        clean_for_json(agg_preview.to_dict(orient="records"))
        if agg_preview is not None
        else []
    )
    fig_json_clean = clean_for_json(fig_json)

    return jsonify(
        {
            "answer": spec.get("insight", ""),
            "figure": fig_json_clean,
            "chart_spec": spec.get("chart", {}),
            "suggested_questions": spec.get("suggested_questions", []),
            "data_preview": data_preview_clean,
            "agg_preview": agg_preview_clean,
            "llm_error": llm_error,
        }
    )


# ---------------------------------------------------------
# API: report download
# ---------------------------------------------------------

@app.route("/api/report/<dataset_id>", methods=["GET"])
@login_required
def api_report(dataset_id: str):
    item = DATASETS.get(dataset_id)
    if not item:
        return jsonify({"error": "Dataset not found"}), 404

    html = build_html_report(dataset_meta=item["meta"], history=item["history"])
    return send_file(
        io.BytesIO(html.encode("utf-8")),
        mimetype="text/html",
        as_attachment=True,
        download_name=f"ADA_Report_{dataset_id[:8]}.html",
    )


# ---------------------------------------------------------
# API: cleanup old uploads
# ---------------------------------------------------------

@app.route("/api/cleanup", methods=["POST"])
@login_required
def api_cleanup():
    now = time.time()
    to_delete = []

    for k, v in list(DATASETS.items()):
        if now - v["created_at"] > KEEP_UPLOAD_MINUTES * 60:
            to_delete.append(k)

    for k in to_delete:
        try:
            os.remove(DATASETS[k]["path"])
        except Exception:
            pass
        DATASETS.pop(k, None)

    return jsonify({"deleted": len(to_delete)})


# ---------------------------------------------------------
# Run
# ---------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)