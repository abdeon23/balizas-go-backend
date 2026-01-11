from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import requests
import xmltodict
import time

app = Flask(__name__)
CORS(app)

# --- Database setup ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///balizas.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Models ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(50))
    xp = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)

# --- Globals ---
DATEX2_URL = "https://nap.dgt.es/datex2/v3/dgt/SituationPublication/datex2_v36.xml"

# --- DATEX2 Parsing ---
def fetch_datex2():
    """Descarga XML DATEX2 v3.6 y lo convierte a dict Python."""
    resp = requests.get(DATEX2_URL, timeout=12)
    resp.raise_for_status()
    xml_text = resp.text
    data = xmltodict.parse(xml_text)
    return data

def extract_balizas_from_datex2(data):
    """
    Extrae solo eventos con <sit:causeType>vehicleObstruction</sit:causeType>.
    Devuelve lista de balizas {id, lat, lng, municipality}.
    """
    balizas = []
    try:
        situations = data.get("d2LogicalModel", {}) \
                         .get("payloadPublication", {}) \
                         .get("situation", [])

        if isinstance(situations, dict):
            situations = [situations]

        for situation in situations:
            records = situation.get("situationRecord", [])
            if isinstance(records, dict):
                records = [records]

            for rec in records:
                # Causa
                cause = rec.get("cause", {})
                cause_type = cause.get("causeType")
                if cause_type != "vehicleObstruction":
                    continue

                # Coordenadas: try "to", then "from"
                loc_ref = rec.get("locationReference", {})
                linear = loc_ref.get("tpegLinearLocation", {})

                lat, lng = None, None

                # To
                to_pt = linear.get("to", {}) \
                               .get("pointCoordinates", {})
                if to_pt:
                    lat = to_pt.get("latitude")
                    lng = to_pt.get("longitude")

                # From fallback
                if not lat or not lng:
                    from_pt = linear.get("from", {}) \
                                     .get("pointCoordinates", {})
                    lat = from_pt.get("latitude")
                    lng = from_pt.get("longitude")

                if not lat or not lng:
                    continue

                # Municipality (localidad)
                municipality = None
                ext = None
                try:
                    ext = to_pt.get("_tpegNonJunctionPointExtension", {}) \
                               .get("extendedTpegNonJunctionPoint", {})
                except Exception:
                    pass
                municipality = ext.get("municipality") if ext else "Desconocida"

                try:
                    lat = float(lat)
                    lng = float(lng)
                except:
                    continue

                rec_id = rec.get("@id", str(time.time()))

                balizas.append({
                    "id": rec_id,
                    "lat": lat,
                    "lng": lng,
                    "municipality": municipality
                })
    except Exception as e:
        print("Error extract_balizas:", e)

    print(f"Balizas filtradas vehicleObstruction: {len(balizas)}")
    return balizas

# --- API Endpoints ---

@app.route("/api/balizas")
def api_balizas():
    try:
        data = fetch_datex2()
        balizas = extract_balizas_from_datex2(data)
        return jsonify(balizas)
    except Exception as e:
        print("Error /api/balizas:", e)
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
    users = User.query.order_by(User.level.desc(), User.xp.desc()).limit(10).all()
    return jsonify([{"username": u.username, "xp": u.xp, "level": u.level} for u in users])

# --- Create DB and Run ---

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
