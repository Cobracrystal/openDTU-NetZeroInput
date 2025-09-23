from flask import Flask, request, redirect, jsonify
import os
import sqlite3
import time

DB_FILE_NAME = "solar_data.db"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.normpath(os.path.join(BASE_DIR, '..', 'data', DB_FILE_NAME))

app = Flask(__name__)

def fetch_data(hours=24):
    """Fetch last N hours of measurements from SQLite."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = int(time.time())
    since = now - hours * 3600
    cursor.execute("""
        SELECT timestamp, inverterLimit, battery, consumption, voltage
        FROM measurements
        WHERE timestamp >= ?
        ORDER BY timestamp ASC
    """, (since,))
    rows = cursor.fetchall()
    conn.close()
    # Convert to list of dicts for JSON
    return [{"timestamp": ts, "inverterLimit": lim, "battery": b, "consumption": c, "voltage": v} for ts, lim, b, c, v in rows]

@app.route("/data.json")
def data_json():
    return jsonify(fetch_data(hours=24))  # last 24 hours

@app.route("/")
def index():
    return app.send_static_file("index.html")  # serve frontend HTML

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
