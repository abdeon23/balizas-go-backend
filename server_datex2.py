import time
import requests
import xml.etree.ElementTree as ET
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------- CONFIG ----------------

DATEX_URL = "https://nap.dgt.es/datex2/v3/dgt/SituationPublication/datex2_v36.xml"
CACHE_SECONDS = 300

NAMESPACES = {
    "sit": "http://datex2.eu/schema/3/situation",
    "loc": "http://datex2.eu/schema/3/location",
    "com": "http://datex2.eu/schema/3/common",
    "lse": "http://datex2.eu/schema/3/locationExtension"
}

# ---------------- APP ----------------

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///game.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
CORS(app)

db = SQLAlchemy(app)

# ---------------- MODELS ----------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    points = db.Column(db.Integer, default=0)

class Help(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    baliza_id = db.Column(db.String(50))

class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    name = db.Column(db.String(100))

# ---------------- INIT ----------------

with app.app_context():
    db.create_all()

# ---------------- DATEX CACHE ----------------

_last_fetch = 0
_cached_balizas = []

def fetch_balizas():
    global _last_fetch, _cached_balizas

    if time.time() - _last_fetch < CACHE_SECONDS:
        return _cached_balizas

    r = requests.get(DATEX_URL, timeout=15)
    root = ET.fromstring(r.content)

    balizas = []

    for situation in root.findall(".//sit:situation", NAMESPACES):

        cause = situation.find(".//sit:causeType", NAMESPACES)
        if cause is None or cause.text != "vehicleObstruction":
            continue

        lat = situation.find(".//loc:latitude", NAMESPACES)
        lon = situation.find(".//loc:longitude", NAMESPACES)

        if lat is None or lon is None:
            continue

        municipality = situation.find(".//lse:municipality", NAMESPACES)
        road = situation.find(".//loc:roadName", NAMESPACES)

        balizas.append({
            "id": situation.attrib.get("id"),
            "lat": float(lat.text),
            "lon": float(lon.text),
            "municipality": municipality.text if municipality is not None else "Desconocido",
            "road": road.text if road is not None else ""
        })

    _cached_balizas = balizas
    _last_fetch = time.time()
    print(f"Balizas extraídas: {len(balizas)}")
    return balizas

# ---------------- ACHIEVEMENTS ----------------

def check_achievements(user):
    total = Help.query.filter_by(user_id=user.id).count()

    achievements = {
        1: "Primera ayuda",
        5: "5 ayudas enviadas",
        10: "10 ayudas enviadas",
        25: "25 ayudas enviadas"
    }

    for qty, name in achievements.items():
        if total >= qty:
            exists = Achievement.query.filter_by(user_id=user.id, name=name).first()
            if not exists:
                db.session.add(Achievement(user_id=user.id, name=name))

    db.session.commit()

# ---------------- API ----------------

@app.route("/api/balizas")
def balizas():
    return jsonify(fetch_balizas())

@app.route("/api/register", methods=["POST"])
def register():
    data = request.json
    if User.query.filter_by(username=data["username"]).first():
        return jsonify({"error": "Usuario ya existe"}), 400

    user = User(
        username=data["username"],
        password=generate_password_hash(data["password"])
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    user = User.query.filter_by(username=data["username"]).first()
    if not user or not check_password_hash(user.password, data["password"]):
        return jsonify({"error": "Credenciales incorrectas"}), 401

    return jsonify({"user_id": user.id, "points": user.points})

@app.route("/api/help", methods=["POST"])
def send_help():
    data = request.json
    user = User.query.get(data["user_id"])

    if not user:
        return jsonify({"error": "Usuario no válido"}), 400

    already = Help.query.filter_by(
        user_id=user.id,
        baliza_id=data["baliza_id"]
    ).first()

    if already:
        return jsonify({"error": "Ya ayudaste"}), 400

    db.session.add(Help(user_id=user.id, baliza_id=data["baliza_id"]))
    user.points += 10
    db.session.commit()

    check_achievements(user)

    return jsonify({"ok": True, "points": user.points})

@app.route("/api/ranking")
def ranking():
    users = User.query.order_by(User.points.desc()).limit(20)
    return jsonify([
        {"username": u.username, "points": u.points}
        for u in users
    ])

@app.route("/api/achievements/<int:user_id>")
def achievements(user_id):
    ach = Achievement.query.filter_by(user_id=user_id)
    return jsonify([a.name for a in ach])

# ---------------- RUN ----------------


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
