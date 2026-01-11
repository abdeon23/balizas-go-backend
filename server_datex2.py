from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import requests
import xml.etree.ElementTree as ET
import time

# ---------------------------
# Configuración básica Flask
# ---------------------------
app = Flask(__name__)
CORS(app)  # Permite que el frontend en otra URL acceda

# ---------------------------
# Configuración SQLite
# ---------------------------
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///game.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ---------------------------
# Modelos de base de datos
# ---------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    score = db.Column(db.Integer, default=0)

class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(200))
    points = db.Column(db.Integer, default=10)

class Mission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200))
    points = db.Column(db.Integer, default=5)

class UserAchievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievement.id'))
    completed = db.Column(db.Boolean, default=False)

# ---------------------------
# Datos de balizas
# ---------------------------
DATEX_URL = "https://nap.dgt.es/datex2/v3/dgt/SituationPublication/datex2_v36.xml"

balizas_cache = []
last_fetch_time = 0
FETCH_INTERVAL = 300  # cada 5 minutos

def fetch_balizas():
    global balizas_cache, last_fetch_time
    now = time.time()
    if now - last_fetch_time < FETCH_INTERVAL:
        return balizas_cache
    try:
        r = requests.get(DATEX_URL, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        balizas = []

        ns = {
            'sit': 'http://levelC/schema/3/situation',
            'loc': 'http://levelC/schema/3/locationReferencing',
            'lse': 'http://levelC/schema/3/locationReferencingSpanishExtension',
            'com': 'http://levelC/schema/3/common'
        }

        for situation in root.findall('sit:situation', ns):
            causeType = situation.find('.//sit:cause/sit:causeType', ns)
            if causeType is not None and causeType.text == 'vehicleObstruction':
                point = situation.find('.//loc:pointCoordinates', ns)
                muni = situation.find('.//lse:municipality', ns)
                if point is not None and muni is not None:
                    lat = float(point.find('loc:latitude', ns).text)
                    lon = float(point.find('loc:longitude', ns).text)
                    balizas.append({
                        'lat': lat,
                        'lon': lon,
                        'municipality': muni.text,
                        'help_sent': False
                    })
        balizas_cache = balizas
        last_fetch_time = now
        print(f"Balizas extraídas: {len(balizas)}")
        return balizas
    except Exception as e:
        print("Error al extraer balizas:", e)
        return []

# ---------------------------
# Rutas API
# ---------------------------
@app.route('/api/balizas')
def api_balizas():
    return jsonify(fetch_balizas())

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Username y password obligatorios'}), 400
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Usuario ya existe'}), 400
    user = User(username=data['username'], password=data['password'])
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'Usuario creado'})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(username=data.get('username')).first()
    if not user or user.password != data.get('password'):
        return jsonify({'error': 'Usuario o password incorrectos'}), 401
    return jsonify({'message': 'Login correcto', 'user_id': user.id})

@app.route('/api/ranking')
def ranking():
    users = User.query.order_by(User.score.desc()).all()
    result = [{'username': u.username, 'score': u.score} for u in users]
    return jsonify(result)

@app.route('/api/achievements')
def achievements():
    achs = Achievement.query.all()
    result = [{'id': a.id, 'name': a.name, 'description': a.description, 'points': a.points} for a in achs]
    return jsonify(result)

@app.route('/api/missions')
def missions():
    missions_list = Mission.query.all()
    result = [{'id': m.id, 'description': m.description, 'points': m.points} for m in missions_list]
    return jsonify(result)


# ---------------------------
# Inicializar DB con logros y misiones
# ---------------------------
def setup_db():
    db.create_all()
    if Achievement.query.count() == 0:
        # 10 logros de ejemplo
        for i in range(1, 11):
            db.session.add(Achievement(
                name=f"Logro {i}", 
                description=f"Descripción del logro {i}", 
                points=i*10
            ))
    if Mission.query.count() == 0:
        # 5 misiones de ejemplo
        for i in range(1, 6):
            db.session.add(Mission(
                description=f"Misión {i}", 
                points=i*5
            ))
    db.session.commit()


# ---------------- RUN ----------------


if __name__ == "__main__":
    setup_db()  # Esto reemplaza before_first_request
    app.run(host="0.0.0.0", port=5000, debug=True)



