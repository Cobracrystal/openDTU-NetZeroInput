from flask import Flask, request, redirect, jsonify, render_template, url_for
import os
import sqlite3
import time
import re
from datetime import datetime

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

def get_cur_logFile():
	return f'{(datetime.now()).strftime("%Y-%m-%d")}_log.txt'

# extract lines with [INFO], [WARNING], [ERROR]
def get_important_logInfo():
	path = get_cur_logFile()
	importantLines = []
	pattern = re.compile("(?:\[ERROR\]|\[WARNING\]|\[INFO\])")
	try:
		with open(path, "r", encoding='UTF-8') as logFile:
			for line in logFile:
				if pattern.match(line):
					importantLines.append(line.strip())
	except FileNotFoundError:
		print(f"Log file {path} not found.")
		importantLines.append(f"Log file {path} not found.")
	return '\n'.join(importantLines)

def get_recent_logInfo(lineCount = 50):
	path = get_cur_logFile()
	counter = 0
	try:
		with open(path, "rb") as f:
			f.seek(0, os.SEEK_END)
			pointer = f.tell()
			while pointer > 0 and counter < lineCount:
				pointer -= 1
				f.seek(pointer)
				if f.read(1) == b'\n':
					counter += 1
			if counter == lineCount:
				f.seek(pointer + 1)
			else:
				f.seek(0)
		return '\n'.join([line.decode('utf-8').strip() for line in f.readlines()])
	except Exception as e:
		str = f"Error reading log file {path}: {e}"
		print(str)
		return str

def get_since_timestamp(minutes):
	return int(time.time()) - (minutes * 60)

def getSolarMetadata():
	return query_db("SELECT inputIndex, name FROM dc_metadata")

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
	
	metadata = getSolarMetadata()
	index_to_pos = {row[0]: i for i, row in enumerate(metadata['values'])}
	row_template = [0.0] * len(metadata['values'])

	since = get_since_timestamp(minutes)
	query = """
		SELECT timestamp, inputIndex, power
		FROM dc_inputs
		WHERE timestamp >= ?
		ORDER BY timestamp ASC
	"""
	result = query_db(query, (since,))
	
	# all of this to avoid repeating the timestamp 300000 times
	grouped = {}
	for timestamp, idx, power in result["values"]: # rows.values != rows["values"] for iterating
		if timestamp not in grouped:
			grouped[timestamp] = list(row_template) # [0.0, 0.0, 0.0, 0.0] or some variation of that
		if idx in index_to_pos:
			grouped[timestamp][index_to_pos[idx]] = power

	grouped_data = [[ts, powers] for ts, powers in sorted(grouped.items())]
	return {
		"columns": [ "timestamp", "power_values" ],
		"mapping": index_to_pos,
		"values": grouped_data
	}

def getSolarVoltage(minutes=1440):
	"""Third: solar panels and battery voltage"""
	
	metadata = getSolarMetadata()
	index_to_pos = {row[0]: i for i, row in enumerate(metadata['values'])}
	row_template = [0.0] * len(metadata['values'])

	since = get_since_timestamp(minutes)
	query = """
		SELECT timestamp, inputIndex, voltage 
		FROM dc_inputs
		WHERE timestamp >= ?
		ORDER BY timestamp ASC
	"""
	result = query_db(query, (since,))
	
	# all of this to avoid repeating the timestamp 300000 times
	grouped = {}
	for timestamp, idx, power in result["values"]: # rows.values != rows["values"] for iterating
		if timestamp not in grouped:
			grouped[timestamp] = list(row_template) # [0.0, 0.0, 0.0, 0.0] or some variation of that
		if idx in index_to_pos:
			grouped[timestamp][index_to_pos[idx]] = power

	grouped_data = [[ts, powers] for ts, powers in sorted(grouped.items())]
	return {
		"columns": [ "timestamp", "voltage_values" ],
		"mapping": index_to_pos,
		"values": grouped_data
	}


##### JSON DATA
@app.route("/dashboard/json/main_data.json")
def main_data():
	return jsonify(getMainData(minutes=1440))

@app.route("/dashboard/json/main_data_update.json")
def main_data_update():
	return jsonify(getMainData(minutes=1))

@app.route("/dashboard/json/solar_power.json")
def solar_power():
	return jsonify(getSolarPower(minutes=1440))

@app.route("/dashboard/json/solar_power_update.json")
def solar_power_update():
	return jsonify(getSolarPower(minutes=1))

@app.route("/dashboard/json/solar_voltage.json")
def solar_voltage():
	return jsonify(getSolarVoltage(minutes=1440))

@app.route("/dashboard/json/solar_voltage_update.json")
def solar_voltage_update():
	return jsonify(getSolarVoltage(minutes=1))

@app.route("/dashboard/json/solar_metadata.json")
def solar_metadata():
	return jsonify(getSolarMetadata())

#### RAW TEXT
@app.route("/dashboard/logs/fullLog.txt")
def fullLog():
	return get_recent_logInfo(lineCount=50000)

@app.route("/dashboard/logs/recentLog.txt")
def recentLog():
	return get_recent_logInfo(lineCount=50)

@app.route("/dashboard/logs/filteredLog.txt")
def filteredLog():
	return get_important_logInfo()

#### HTML

@app.route("/")
def redirect_dashboard():
	return redirect(url_for('dashboardMain'))

@app.route("/dashboard")
@app.route("/dashboard/main")
def dashboardMain():
	return render_template("indexMain.html", active_page="main")

@app.route("/dashboard/individualPower")
def dashboardIndividualPower():
	return render_template("indexPower.html", active_page="individualPower")

@app.route("/dashboard/individualVoltage")
def dashboardIndividualVoltage():
	return render_template("indexVoltage.html", active_page="individualVoltage")

if __name__ == "__main__":
	app.run(host="0.0.0.0", port=5000, debug=True)
