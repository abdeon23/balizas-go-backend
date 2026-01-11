from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import requests
import xmltodict
import time

app = Flask(__name__)
CORS(app)  # Permite llamadas desde cualquier origen
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///balizas.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

DATEX2_URL = "https://nap.dgt.es/datex2/v3/dgt/SituationPublication/incidencias.xml"

# -------------------
# MODELOS DE DATOS
# -------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(50))  # simple para demo
    xp = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)

class Mission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    description = db.Column(db.String(200))
    completed = db.Column(db.Boolean, default=False)
    xp_reward = db.Column(db.Integer, default=0)

class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    name = db.Column(db.String(100))
    earned = db.Column(db.Boolean, default=False)

# -------------------
# UTILIDADES DATEX2
# -------------------
def fetch_datex2():
    resp = requests.get(DATEX2_URL, timeout=10)
    resp.raise_for_status()
    xml_text = resp.text
    data = xmltodict.parse(xml_text)
    return data

def extract_balizas_from_datex2(data):
    balizas = []
    try:
        situations = data.get('d2:payload', {}).get('sit:situation', [])
        if isinstance(situations, dict):
            situations = [situations]
        for sit in situations:
            records = sit.get('sit:situationRecord', [])
            if isinstance(records, dict):
                records = [records]
            for rec in records:
                loc_ref = rec.get('sit:locationReference', {})
                to_point = loc_ref.get('loc:tpegLinearLocation', {}).get('loc:to', {}).get('loc:pointCoordinates', {})
                from_point = loc_ref.get('loc:tpegLinearLocation', {}).get('loc:from', {}).get('loc:pointCoordinates', {})
                if to_point and 'loc:latitude' in to_point and 'loc:longitude' in to_point:
                    lat = float(to_point['loc:latitude'])
                    lng = float(to_point['loc:longitude'])
                elif from_point and 'loc:latitude' in from_point and 'loc:longitude' in from_point:
                    lat = float(from_point['loc:latitude'])
                    lng = float(from_point['loc:longitude'])
                else:
                    continue
                municipality = to_point.get('loc:_tpegNonJunctionPointExtension', {}).get('loc:extendedTpegNonJunctionPoint', {}).get('lse:municipality', 'Desconocida')
                balizas.append({
                    "id": rec.get('@id', str(time.time())),
                    "lat": lat,
                    "lng": lng,
                    "municipality": municipality
                })
    except Exception as e:
        print("Error extrayendo balizas:", e)
    return balizas

# -------------------
# RUTAS
# -------------------

@app.route("/api/balizas")
def api_balizas():
    try:
        data = fetch_datex2()
        balizas = extract_balizas_from_datex2(data)
        return jsonify(balizas)
    except Exception as e:
        print("Error en /api/balizas:", e)
        return jsonify({"error": "No se pudieron obtener balizas"}), 500

@app.route("/api/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Usuario ya existe"}), 400
    user = User(username=username, password=password)
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "Usuario creado"}), 201

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    user = User.query.filter_by(username=username, password=password).first()
    if not user:
        return jsonify({"error": "Usuario o contraseña incorrecta"}), 400
    return jsonify({
        "id": user.id,
        "username": user.username,
        "xp": user.xp,
        "level": user.level
    })

@app.route("/api/send_help", methods=["POST"])
def send_help():
    data = request.json
    user_id = data.get("user_id")
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 400
    user.xp += 20
    if user.xp >= 100:
        user.level += 1
        user.xp -= 100
    db.session.commit()
    return jsonify({"xp": user.xp, "level": user.level})

@app.route("/api/ranking")
def ranking():
    users = User.query.order_by(User.xp.desc(), User.level.desc()).limit(10).all()
    return jsonify([{"username": u.username, "xp": u.xp, "level": u.level} for u in users])

# -------------------
# INICIO
# -------------------
if __name__ == "__main__":
    db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
