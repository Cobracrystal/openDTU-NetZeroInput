from enum import Enum, auto
import time
import suntime
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from openDTU import *
from dateutil import tz
from colorama import Fore, Style, Back
from colorama import init as colorama_init
import re
import os
import sqlite3

# CONFIGURATION
username = "admin"
password = open(r"openDTUAuth.pw").read().strip()
urlOpenDTU = "http://192.168.178.31"
urlBitshake = "http://192.168.178.40"
portOpenDTU = 80
latitude = 50.988768 # for calculating sunrise/sunset
longitude = 7.190650 # for calculating sunrise/sunset
update_interval = 3 # Time in seconds between each update to dtu limit
saveInterval = 5 # Time in seconds between each write to database. Datapoints are gotten every second regardless
checkInterval = 1 # Time in seconds between each check
logInTextFile = True # Enable if you want all console output to be logged
storeData = True # Whether to store received data in SQL
battery_voltage_thresholds = [48.8, 49.2, 49.6] # Threshold below which connection with battery is reduced.
battery_voltage_threshold_caps = [0, 0.5, 0.75] # Multipliers for max_power (caps max power for inverter when corresponding threshold is reached)
battery_voltage_recovery_buffers = [1.7, 0.7, 0.6] # Multipliers for max_power (caps max power for inverter when corresponding threshold is reached)
DB_FILE = "solar_data.db"


@dataclass
class DCInput:
	index: int # solar panel or battery
	name: str # name of the input (eg battery or west)
	power: float # dc power delivery of the input
	voltage: float # voltage of the input

@dataclass
class SolarMeasurements:
	timestamp: int # current time
	inverter_limit: float # the limit of the inverter as an absolute value
	ac_power_output: float # the current AC power delivery
	grid_consumption: float # the grid consumption value (if balanced, is around 0W)
	dc_list: list[DCInput] # list of individual DC inputs (battery + solar panels)

class LogStyle(Enum):
	DEFAULT = auto()
	WARNING = auto()
	INFO = auto()
	ERROR = auto()
	
def getFileName():
	return f'{(datetime.now()).strftime("%Y-%m-%d")}'

# For multiline-styles, requires setting that style for each line.
def log(text, style=LogStyle.DEFAULT):
	fdate = datetime.now().strftime("%H:%M:%S")
	timestamp_raw = f'[{fdate}]'
	timestamp = f'{Fore.LIGHTYELLOW_EX}{timestamp_raw}{Style.RESET_ALL}'
	BADEVENT_COLOR = f'{Back.LIGHTRED_EX}{Fore.BLACK}'
	styles = {
		LogStyle.DEFAULT: "",
		LogStyle.WARNING: f'{BADEVENT_COLOR}[WARNING]{Style.RESET_ALL} ',
		LogStyle.INFO: f'{Back.LIGHTYELLOW_EX}{Fore.BLACK}[INFO]{Style.RESET_ALL} ',
		LogStyle.ERROR: f'{BADEVENT_COLOR}[ERROR] ' # the entire error message is red
	}
	tags_raw = {
		LogStyle.DEFAULT: "",
		LogStyle.WARNING: f'[WARNING] ',
		LogStyle.INFO: f'[INFO] ',
		LogStyle.ERROR: f'[ERROR] '
	}
	prefix_width = len(timestamp_raw) + 1 + len(tags_raw.get(style, ""))
	indent = " " * prefix_width
	lines = str(text).splitlines()
	logOutput = ""
	for i, line in enumerate(lines):
		if i == 0:
			line_content = f"{timestamp} {styles.get(style, '')}{line}"
		elif style is LogStyle.ERROR:
			line_content = f"{indent}{BADEVENT_COLOR}{line}"
		else:
			line_content = f"{indent}{line}"
		print(line_content + Style.RESET_ALL)
		logOutput += line_content + '\n'
	if logInTextFile:
		fName = getFileName() + '_log.txt'
		try:
			with open(fName, "a+") as f:
				clean_text = re.sub(r'\x1b\[[0-9;]*[mGKH]', '', logOutput)
				f.write(clean_text)
		except Exception as e:
			print(f'{timestamp} {BADEVENT_COLOR}ERROR: FAILED TO WRITE TO LOG FILE.{Style.RESET_ALL}')

def initSQLMetadata(dc_list: list[DCInput]):
	""" To make sure all current DC inputs are registered in the metadata table."""
	metadata_rows = [(dc.index, dc.name) for dc in dc_list]
	try:
		cursor.executemany(
			"INSERT OR REPLACE INTO dc_metadata (inputIndex, name) VALUES (?, ?)",
			metadata_rows
		)
		conn.commit()
		return True
	except sqlite3.Error as e:
		log(f"Metadata sync failed: {e}", LogStyle.ERROR)
		return False
	
def saveSQL():
	global data_buffer, metadataIsSynced
	if not data_buffer:
		return
	rows_measurement = []
	rows_dc_input = []
	if not metadataIsSynced:
		metadataIsSynced = initSQLMetadata(data_buffer[-1].dc_list)
	for dataPoint in data_buffer:
		rows_measurement.append((
			dataPoint.timestamp, 
            dataPoint.inverter_limit, 
            dataPoint.ac_power_output, 
            dataPoint.grid_consumption
		))
		for dc in dataPoint.dc_list:
			rows_dc_input.append((
				dataPoint.timestamp,
				dc.index,
				dc.power,
				dc.voltage
			))
	try:
		cursor.executemany("INSERT OR IGNORE INTO measurements VALUES (?, ?, ?, ?)", rows_measurement)
		cursor.executemany("INSERT OR IGNORE INTO dc_inputs VALUES (?, ?, ?, ?)", rows_dc_input)
		conn.commit()
	except sqlite3.Error as e:
		log(f'Saving failed: {e}', style=LogStyle.ERROR)
		conn.rollback()
	finally:
		data_buffer.clear()

def clamp(value, lower, upper):
	return max(lower, min(upper, value))

def validate_consumption(new_value):
	global grid_history
	# these values are ALWAYS false, so don't bother updating history or any other checks
	if new_value > 50000 or new_value < -10000:
		log(f"Ignoring impossible BitMeter reading: {new_value}W", LogStyle.WARNING)
		return grid_history[-1]
	last_value = grid_history[-1]
	# update sliding window
	grid_history.append(new_value)
	if len(grid_history) > 3: # in theory this should always be true. in theory.
		grid_history.pop(0)
	if abs(new_value - last_value) < 2000: # should be correct
		return new_value
	else: # unsure
		better_value = sorted(grid_history)[1]
		log(f"Validating suspicious Bitmeter reading: {new_value}W -> {better_value}W", LogStyle.WARNING)
		return better_value
	
def get_openDTU_data():
	global main_inverter
	try:
		# make request
		if main_inverter is None:
			main_inverter = dtu.inverterGetSerial(0)
		inverter_limit_config = dtu.inverterGetLimitConfig()
		runtime_info = dtu.inverterGetRuntimeInfo(main_inverter)
		return inverter_limit_config, runtime_info
	except requests.exceptions.Timeout:
		log(f"OpenDTU request timed out.", LogStyle.ERROR)
		return None
	except requests.exceptions.RequestException as e:
		log(f"Request to openDTU failed with exception {e}", LogStyle.ERROR)
		return None
	except BaseException as e:
		if type(e) == KeyboardInterrupt:
			raise
		log(f"Could not parse data from openDTU: {e}", LogStyle.ERROR)
		return None
	
def get_BitMeter_data():
	try:
		response = requests.get(url = f'{urlBitshake}/cm?cmnd=status 10', timeout=10)
		if response.status_code == 200:
			bitMeter_data = response.json()
			return bitMeter_data["StatusSNS"]["LK13BE"]["Power"]
		else:
			log(f"BitMeter returned Status Code {response.status_code}", LogStyle.ERROR)
			return None
	except requests.exceptions.Timeout:
		log(f"BitMeter request timed out.", LogStyle.ERROR)
		return None
	except requests.exceptions.RequestException as e:
		log(f"Request to BitMeter failed with exception {e}", LogStyle.ERROR)
		return None
	except BaseException as e:
		if type(e) == KeyboardInterrupt:
			raise
		return None
	
def update():
	global ticks, main_inverter, inverterWasReachable, limitWasUnchanged, batteryWasBelowLastThresholds, batteryWasOff, last_save_time
	ticks += 1
	now = int(time.time())

	# Get DTU Data
	openDTU_data = get_openDTU_data()
	if openDTU_data is None:
		return False
	inverter_limit_config, runtime_info = openDTU_data
	# get DC Inputs
	solarIsOn = False
	solar_power, battery_power, battery_voltage = 0, 0, 0
	current_dc_inputs = []
	inverter_info = runtime_info['inverters'][0]
	for index, source in inverter_info['DC'].items():
		power = source['Power']['v']
		voltage = source['Voltage']['v']
		name = source['name']['u']
		current_dc_inputs.append(DCInput(
			index=int(index),
			name=name,
			power=power,
			voltage=voltage
		))
		if 'batterie' in name.lower():
			battery_power = power
			battery_voltage = voltage
		else:
			solar_power += power
			if voltage > 2:
				solarIsOn = True
	batteryIsOn = battery_power > 0
	old_limit_r = float(inverter_info['limit_relative'])
	old_limit_a = round(inverter_info['limit_absolute'])
	# total_dc_power_input = inverter_info['INV']['0']['Power DC']['v'] # EQUIVALENT TO SUMMING OVER dc_input
	# ac_dc_conversion_ratio = inverter_info['INV']['0']['Efficiency']['v'] / 100 # EQUIVALENT TO ac_delivery / dc_delivery
	ac_power_output = runtime_info['total']['Power']['v'] # AC power output
	# total_power_delivery = inverter_info['AC']['0']['Power']['v'] # equivalent to above since only one AC output
	max_power = inverter_limit_config[main_inverter]['max_power']
	# inverterIsProducing = inverter_info['producing']
	inverterIsReachable = inverter_info['reachable']
	limit_set_status = inverter_limit_config[main_inverter]['limit_set_status']

	# Bitmeter data
	grid_power_consumption = get_BitMeter_data()
	if grid_power_consumption is None: # request threw exception -> return. Do not use try so that keyboard interrupts all the way up)
		return False
	grid_power_consumption = validate_consumption(grid_power_consumption)
	if storeData and last_save_time != now: # store data every second
		data_buffer.append(SolarMeasurements(
			timestamp=now,
			inverter_limit=old_limit_a,
			ac_power_output=ac_power_output,
			grid_consumption=grid_power_consumption,
			dc_list=current_dc_inputs
		))
		last_save_time = now
	if storeData and ticks % (saveInterval // checkInterval) == 0:
		saveSQL()
	# wechselrichter nicht erreichbar -> limit kann eh nicht gesetzt werden -> skip
	if not inverterIsReachable:
		if inverterWasReachable:
			inverterWasReachable = False
			if batteryWasOff and not batteryIsOn:
				log("No connection to inverter. Battery was and is offline, so no actions necessary.", LogStyle.INFO)
			else:
				log('No connection to inverter. Battery was on, so this is unusual. Skipping logs until reachable.', LogStyle.INFO)
		return False
	# Nur updaten wenn update_interval verstrichen ist
	if ticks % (update_interval // checkInterval) != 0:
		return True
	# Wechselrichter ist erreichbar
	if not inverterWasReachable:
		inverterWasReachable = True
		if batteryWasOff and not batteryIsOn:
			log("Reestablished connection to inverter. Battery is still off, continue waiting.", LogStyle.INFO)
		else:
			log('Reestablished connection to inverter. Continuing script.', LogStyle.INFO)
	# Wechselrichter gibt nicht old_limit_a Watt aus, sondern weniger, außer das limit ist 0.
	if ac_power_output > 0 and old_limit_a > 0:
		limit_ratio = old_limit_a / ac_power_output
	else:
		limit_ratio = 1
	if batteryIsOn:
		if batteryWasOff:
			log('Battery is delivering electricity again. Continuing script.', LogStyle.INFO)
			batteryWasOff = False
		# Calculate base limit. Will be clamped to max_power later.
		new_limit_a = round(limit_ratio * (grid_power_consumption + ac_power_output)) # works even if negative.
		
		active_threshold_index = -1
		for i in range(len(battery_voltage_thresholds)):
			target = battery_voltage_thresholds[i]
			if batteryWasBelowLastThresholds[i]: # add recovery buffer if we already went below the threshold (hysteresis?)
				target += battery_voltage_recovery_buffers[i]
			if battery_voltage < target: # we are still below the target. this obviously only works if we iterate from the lowest to the highest threshold.
				active_threshold_index = i
				break
		if active_threshold_index != -1:
			i = active_threshold_index
			if not batteryWasBelowLastThresholds[i]: # Log once.
				batteryWasBelowLastThresholds = [False] * len(battery_voltage_thresholds)
				batteryWasBelowLastThresholds[i] = True
				recovery_voltage = battery_voltage_thresholds[i]+battery_voltage_recovery_buffers[i]
				log(f'Battery voltage ({battery_voltage}V) below threshold {i+1} ({battery_voltage_thresholds[i]}V).', LogStyle.INFO)
				log(f'Capping Limit to {battery_voltage_threshold_caps[i] * 100}% until voltage drops below additional threshold or rises above {recovery_voltage}V again. (Threshold + Buffer)', LogStyle.INFO)
			else:
				if battery_voltage_threshold_caps[i] == 0:
					return False
			max_power *= battery_voltage_threshold_caps[i]
		else:
			if any(batteryWasBelowLastThresholds):
				log(f'Battery voltage is above threshold again ({battery_voltage}V). Lifting all Caps.', LogStyle.INFO)
				batteryWasBelowLastThresholds = [False] * len(battery_voltage_thresholds)
	else:
		if batteryWasOff: # Battery was off, so it stays off
			return True
		batteryWasOff = True
		if solarIsOn:
			log(f'Battery is off ({battery_voltage}V), solar panels are delivering power ({solar_power}W). Setting Limit to 100 and sleep.', LogStyle.INFO)
			new_limit_a = max_power
			batteryWasBelowLastThresholds = False # Reset on the new day
		else:
			log(f'Battery is off ({battery_voltage}V), solar panels are not delivering power ({solar_power}W). Setting Limit to 0 and sleep.', LogStyle.INFO)
			new_limit_a = 0
	new_limit_a = clamp(new_limit_a, 0, max_power)
	new_limit_r = round(100 * new_limit_a / max_power, ndigits=1) if max_power > 0 else 0 # necessary to avoid division by 0
	consumption_color = Fore.LIGHTRED_EX if grid_power_consumption >= 0 else Fore.LIGHTGREEN_EX
	log(f"Grid Draw:\t{consumption_color}{grid_power_consumption}W{Style.RESET_ALL} | "
	 	f"Inverter Limit: {Fore.LIGHTWHITE_EX}{old_limit_r:}% / {old_limit_a}W{Style.RESET_ALL}.")
	log(f'Total Inverter Output: {Fore.LIGHTCYAN_EX}{ac_power_output}W. (Solar: {solar_power}W : Battery: {battery_power}W)')
	if (new_limit_a != old_limit_a):
		# wechselrichter beschäftigt -> skip
		if limit_set_status == "Pending":
			log(f'New Limit would be {Fore.LIGHTCYAN_EX}{new_limit_r}% / {new_limit_a}W{Style.RESET_ALL}, but inverter is busy. Skipping.', LogStyle.WARNING)
			return True
		log(f'New Limit: {Fore.LIGHTCYAN_EX}{new_limit_r}% / {new_limit_a}W{Style.RESET_ALL} ({round(new_limit_a/limit_ratio)} = {grid_power_consumption} + {ac_power_output})')
		setLimitResponse = dtu.inverterSetLimitConfig(main_inverter, {"limit_type":0, "limit_value":new_limit_a})
		limitWasUnchanged = False
		if (setLimitResponse['type'] != "success"):
			log(f'Could not set inverter limit: {setLimitResponse}', LogStyle.ERROR)
	elif not limitWasUnchanged:
		log("Current and new Limit match, no update necessary.")
		limitWasUnchanged = True
	return True

# EXECUTE SECTION
colorama_init()

sun = suntime.Sun(lat=latitude, lon=longitude)
sunset = sun.get_sunset_time(time_zone=tz.gettz("Europe/Berlin"))
sunrise = sun.get_sunrise_time(time_zone=tz.gettz("Europe/Berlin"))

# INIT VARIABLES
dtu = openDTU(urlOpenDTU, portOpenDTU, username, password)
ticks = 0
main_inverter = None
inverterWasReachable = True
limitWasUnchanged = False
batteryWasBelowLastThresholds = [False, False, False]
batteryWasOff = False
solarWasOn = True
last_save_time = 0
# grid_history = [0, 0, 0] Its initialized further down
data_buffer = []
metadataIsSynced = False

os.chdir('data') # set working directory
log(f'Program Start: [{(datetime.now()).strftime("%Y-%m-%d %H:%M:%S")}]')
log(f'Sunrise: {sunrise.time()}, Sunset: {sunset.time()}')
log(f'Starting..')

# SQL INIT
conn = sqlite3.connect(DB_FILE, timeout=5)
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("""
CREATE TABLE IF NOT EXISTS measurements (
	timestamp INTEGER PRIMARY KEY,
    inverterLimit REAL,
    acPowerOutput REAL, 
    gridConsumption REAL
)
""")
conn.execute("""
CREATE TABLE IF NOT EXISTS dc_metadata (
    inputIndex INTEGER PRIMARY KEY,
    name TEXT UNIQUE
)
""")
conn.execute("""
CREATE TABLE IF NOT EXISTS dc_inputs (
    timestamp INTEGER,
    inputIndex INTEGER,
    power REAL,
    voltage REAL,
    FOREIGN KEY(timestamp) REFERENCES measurements(timestamp)
    FOREIGN KEY(inputIndex) REFERENCES dc_metadata(inputIndex)
)
""")
conn.commit()
cursor = conn.cursor()

# Seed the history to prevent a 0
grid_power_seed_value = get_BitMeter_data()
if grid_power_seed_value is None:
	grid_history = [0, 0, 0]
else:
	grid_history = [grid_power_seed_value] * 3 

# MAIN LOOP
try:
	next_time = time.time()
	while True:
		flag = update()
		if flag:
			next_time += checkInterval
		else:
			next_time += 4 * checkInterval
		sleep_time = next_time - time.time()
		if sleep_time > 0:
			time.sleep(sleep_time)
		elif sleep_time < -10 and ticks % 30 == 0:
			log(f"Script is {round(abs(sleep_time),ndigits=1)} seconds behind!", LogStyle.WARNING)
except KeyboardInterrupt:
	log('User Interruption. Closing...', LogStyle.INFO)