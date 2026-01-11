from flask import Flask, jsonify
from flask_cors import CORS   # <--- añade esto
import requests
import xmltodict
import time
import sqlite3

app = Flask(__name__)
CORS(app)  # <--- esto permite CORS para todo el backend

DATEX2_URL = "https://nap.dgt.es/datex2/v3/dgt/SituationPublication/datex2_v36.xml"

# Cache simple para no descargar a cada request
cache = {"timestamp": 0, "data": []}
CACHE_TTL = 60  # segundos

def init_db():
    conn = sqlite3.connect('balizas.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            last_update TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def fetch_datex2():
    now = time.time()
    if now - cache["timestamp"] < CACHE_TTL:
        return cache["data"]

    try:
        resp = requests.get(DATEX2_URL, timeout=10)
        resp.raise_for_status()
        xml_text = resp.content
        data = xmltodict.parse(xml_text)
        cache["timestamp"] = now
        cache["data"] = data
        print("Datos descargados y parseados correctamente")
        return data
    except Exception as e:
        print("Error descargando DATEX2:", e)
        return None

def extract_balizas_from_datex2(data):
    balizas = []
    try:
        situations = data.get("d2:payload", {}).get("sit:situation", [])
        if isinstance(situations, dict):
            situations = [situations]
        elif not situations:
            situations = []

        for situation in situations:
            records = situation.get("sit:situationRecord", [])
            if isinstance(records, dict):
                records = [records]

            for rec in records:
                loc_ref = rec.get("sit:locationReference", {})
                tpeg = loc_ref.get("loc:tpegLinearLocation", {})
                from_pt = tpeg.get("loc:from", {}).get("loc:pointCoordinates", {})
                to_pt = tpeg.get("loc:to", {}).get("loc:pointCoordinates", {})

                # Tomamos el punto "from" si existe
                lat = from_pt.get("loc:latitude")
                lng = from_pt.get("loc:longitude")

                if lat is None or lng is None:
                    continue
                try:
                    lat = float(lat)
                    lng = float(lng)
                except:
                    continue

                # Nombre de la carretera o descripción
                road = loc_ref.get("loc:supplementaryPositionalDescription", {}).get("loc:roadInformation", {}).get("loc:roadName", "Desconocida")

                rec_id = rec.get("@id", situation.get("@id", "sin-id"))

                balizas.append({
                    "id": str(rec_id),
                    "lat": lat,
                    "lng": lng,
                    "description": f"Incidencia en {road}"
                })

    except Exception as e:
        print("Error extrayendo balizas:", e)

    print(f"Balizas extraídas: {len(balizas)}")
    return balizas

@app.route("/api/balizas")
def api_balizas():
    data = fetch_datex2()
    if not data:
        return jsonify({"error": "No se pudieron obtener balizas"}), 500

    balizas = extract_balizas_from_datex2(data)
    return jsonify(balizas)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    if not username:
        return jsonify({"error": "No username provided"}), 400

    conn = sqlite3.connect('balizas.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users (username, last_update) VALUES (?, ?)', (username, time.time()))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Username already exists"}), 400

    conn.close()
    return jsonify({"message": f"User {username} registered successfully"}), 201

@app.route('/updateProgress', methods=['POST'])
def update_progress():
    data = request.json
    username = data.get('username')
    xp = data.get('xp')
    level = data.get('level')

    if not username or xp is None or level is None:
        return jsonify({"error": "Missing fields"}), 400

    conn = sqlite3.connect('balizas.db')
    c = conn.cursor()
    c.execute('UPDATE users SET xp = ?, level = ?, last_update = ? WHERE username = ?', (xp, level, time.time(), username))
    conn.commit()
    conn.close()

    return jsonify({"message": "Progress updated successfully"})

@app.route('/getRanking')
def get_ranking():
    conn = sqlite3.connect('balizas.db')
    c = conn.cursor()
    c.execute('SELECT username, xp, level FROM users ORDER BY level DESC, xp DESC LIMIT 10')
    rows = c.fetchall()
    conn.close()
    ranking = [{"username": r[0], "xp": r[1], "level": r[2]} for r in rows]
    return jsonify(ranking)
