from flask import Flask, request, redirect, jsonify, render_template
import os
import sqlite3
import time

DB_FILE_NAME = "solar_data.db"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.normpath(os.path.join(BASE_DIR, '..', 'data', DB_FILE_NAME))

BATTERY_NAME = "Batterie-Lader"

app = Flask(__name__)

def query_db(query, args=()):
	conn = sqlite3.connect(DB_FILE)
	cur = conn.cursor()
	cur.execute(query, args)
	columns = [column[0] for column in cur.description]
	data = cur.fetchall()
	conn.close()
	return {
		"columns": columns,
		"values": data
	}

def get_since_timestamp(minutes):
	return int(time.time()) - (minutes * 60)

def getMainData(minutes=1440):
	"""Timestamp, Inverter Limit, Battery Power, Battery Voltage, Grid Consumption"""
	since = get_since_timestamp(minutes)
	query = """
		SELECT m.timestamp, m.inverterLimit, m.gridConsumption, d.power as batteryPower, d.voltage as batteryVoltage
		FROM measurements m
		JOIN dc_inputs d ON m.timestamp = d.timestamp
		JOIN dc_metadata meta ON d.inputIndex = meta.inputIndex
		WHERE m.timestamp >= ? AND meta.name = ?
		ORDER BY m.timestamp ASC
	"""
	return query_db(query, (since, BATTERY_NAME))

def getSolarPower(minutes=1440):
	"""Secondary: all solar panels and battery power"""
	since = get_since_timestamp(minutes)
	query = """
		SELECT timestamp, inputIndex, power
		FROM dc_inputs
		WHERE timestamp >= ?
		ORDER BY timestamp ASC
	"""
	return query_db(query, (since,))

def getSolarVoltage(minutes=1440):
	"""Third: solar panels and battery voltage"""
	since = get_since_timestamp(minutes)
	query = """
        SELECT timestamp, inputIndex, voltage 
        FROM dc_inputs
        WHERE timestamp >= ?
        ORDER BY timestamp ASC
    """
	return query_db(query, (since,))

@app.route("/main_data.json")
def main_data():
	return jsonify(getMainData(minutes=1440))

@app.route("/main_data_update.json")
def main_data_update():
	return jsonify(getMainData(minutes=1))

@app.route("/solar_metadata.json")
def get_metadata():
	return jsonify(query_db("SELECT inputIndex, name FROM dc_metadata"))

@app.route("/solar_power.json")
def solar_power():
	return jsonify(getSolarPower(minutes=1440))

@app.route("/solar_power_update.json")
def solar_power_update():
	return jsonify(getSolarPower(minutes=1))

@app.route("/solar_voltage.json")
def solar_voltage():
	return jsonify(getSolarVoltage(minutes=1440))

@app.route("/solar_voltage_update.json")
def solar_voltage_update():
	return jsonify(getSolarVoltage(minutes=1))

@app.route("/")
def index():
	return render_template("indexMain.html")

@app.route("/power")
def indexPower():
	return render_template("indexPower.html")

@app.route("/voltage")
def indexVoltage():
	return render_template("indexVoltage.html")

if __name__ == "__main__":
	app.run(host="0.0.0.0", port=5000, debug=True)
