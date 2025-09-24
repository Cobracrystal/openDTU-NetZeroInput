import time
import suntime
from datetime import datetime, timedelta
import pickle
from openDTU import *
from dateutil import tz
from colorama import Fore, Style, Back
from colorama import init as colorama_init
import re
import os
import sqlite3
username = "admin"
password = open(r"openDTUAuth.pw").read().strip()
urlOpenDTU = "http://192.168.178.48"
urlBitshake = "http://192.168.178.40"
portOpenDTU = 80
latitude = 50.988768 # for calculating sunrise/sunset
longitude = 7.190650 # for calculating sunrise/sunset
update_interval = 3 # Time in seconds between each update to dtu limit
saveInterval = 5 # Time in seconds between each write to database. Datapoints are gotten every second regardless
checkInterval = 1 # Time in seconds between each check
logInTextFile = True # Enable if you want all console output to be logged
storeData = True # Whether to store received data in SQL
battery_voltage_threshold = 48.5 # Threshold below which connection with battery is stopped.
DB_FILE = "solar_data.db"

colorama_init()

sun = suntime.Sun(lat=latitude, lon=longitude)
sunset = sun.get_sunset_time(time_zone=tz.gettz("Europe/Berlin"))
sunrise = sun.get_sunrise_time(time_zone=tz.gettz("Europe/Berlin"))

os.chdir('data')
conn = sqlite3.connect(DB_FILE, timeout=5)
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("""
CREATE TABLE IF NOT EXISTS measurements (
	timestamp INTEGER PRIMARY KEY,
	inverterLimit REAL,
	battery REAL,
	consumption REAL,
	voltage REAL
)
""")
conn.commit()
cursor = conn.cursor()

def log(text):
	fdate = datetime.now().strftime("%H:%M:%S")
	print(f'{Fore.LIGHTYELLOW_EX}[{fdate}]{Style.RESET_ALL} {text}{Style.RESET_ALL}')
	fName = getFileName() + '_log.txt'
	if logInTextFile:
		try:
			f = open(fName, "a+")
			text = re.sub(r'\x1b\[\d+m', '', text)
			f.write(f"[{fdate}] {text}" + '\n')
		finally:
			f.close()

def getFileName():
	return f'{(datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d")}'

def saveSQL():
	global data_timestamps, data_oldLimits, data_powerDelivery, data_powerConsumption, data_batteryVoltage
	try:
		rows = list(zip(data_timestamps, data_oldLimits, data_powerDelivery, data_powerConsumption, data_batteryVoltage))
		if not rows:
			return
		cursor.executemany("""
			INSERT INTO measurements (timestamp, inverterLimit, battery, consumption, voltage)
			VALUES (?, ?, ?, ?, ?)
		""", rows)
		conn.commit()
		data_timestamps, data_oldLimits, data_powerDelivery, data_powerConsumption, data_batteryVoltage = [], [], [], [], []
	except sqlite3.Error as e:
		log(f'{Back.LIGHTRED_EX}{Fore.BLACK}Speichern fehlgeschlagen: {e}')


log(f'Programmstart: [{(datetime.now()).strftime("%Y-%m-%d %H:%M:%S")}]')
log(f'Sonnenaufgang: {sunrise.time()}, Sonnenuntergang: {sunset.time()}')

# DO NOT EDIT. INITIALIZING VARIABLES
dtu = openDTU(urlOpenDTU, portOpenDTU, username, password)
ticks = 0
main_inverter = False
inverterWasReachable = True
limitWasUnchanged = False
batteryWasBelowThreshold = False
batteryWasOff = False
solarWasOn = True
last_save_time = 0
last_power_consumption = 0
data_timestamps, data_oldLimits, data_powerDelivery, data_powerConsumption, data_batteryVoltage = [], [], [], [], []

log(f'Starte..')

def update():
	global ticks, main_inverter, inverterWasReachable, limitWasUnchanged, batteryWasBelowThreshold, batteryWasOff, last_save_time, last_power_consumption
	ticks += 1
	now = int(time.time())
	try:
		if not main_inverter:
			main_inverter = dtu.inverterGetSerial(0)
		inverter_limit_config = dtu.inverterGetLimitConfig()
		runtime_info = dtu.inverterGetRuntimeInfo(main_inverter)
		inverter_info = runtime_info['inverters'][0]
		inverterIsReachable = inverter_info['reachable']
		inverterIsProducing = inverter_info['producing']
		solar_power = 0
		solar_voltage = 0
		for index in inverter_info['DC']: # inverter sources
			source = inverter_info['DC'][index]
			if 'batterie' in source['name']['u'].lower():
				battery_power = source['Power']['v']
				battery_voltage = source['Voltage']['v']
			else:
				solar_power += source['Power']['v']
				solar_voltage += source['Voltage']['v']
		solar_voltage /= len(inverter_info['DC']) # average over all solar panels
		solarIsOn = solar_voltage > 0
		batteryIsOn = battery_power > 0
		old_limit_r = float(inverter_info['limit_relative'])
		old_limit_a = round(inverter_info['limit_absolute'])
		current_dc_power_delivery = inverter_info['INV']['0']['Power DC']['v']
		ac_dc_conversion_ratio = inverter_info['INV']['0']['Efficiency']['v'] / 100
		current_power_delivery = runtime_info['total']['Power']['v']
		max_power = inverter_limit_config[main_inverter]['max_power']
		limit_set_status = inverter_limit_config[main_inverter]['limit_set_status']
	except BaseException as e:
		if type(e) == KeyboardInterrupt:
			raise
		log(f"{Back.LIGHTRED_EX}{Fore.BLACK}Fehler{Style.RESET_ALL} bei der Datenabfrage von openDTU: {e}")
		return False
	
	try:
		bitMeter_data = requests.get(url = f'{urlBitshake}/cm?cmnd=status 10').json()
		current_power_consumption = bitMeter_data["StatusSNS"]["LK13BE"]["Power"]
		# remove single spikes
		lastValue = last_power_consumption
		last_power_consumption = current_power_consumption
		if abs(current_power_consumption - lastValue) > 5000:
			current_power_consumption = lastValue
	except BaseException as e:
		if type(e) == KeyboardInterrupt:
			raise
		log(f'{Back.LIGHTRED_EX}{Fore.BLACK}Fehler{Style.RESET_ALL} bei Datenabfrage von BitMeter.')
		return False
	if storeData and last_save_time != now: # store data every second
		data_timestamps.append(now)
		data_oldLimits.append(old_limit_a)
		data_powerDelivery.append(current_power_delivery)
		data_powerConsumption.append(current_power_consumption)
		data_batteryVoltage.append(battery_voltage)
		last_save_time = now
	if storeData and ticks % (saveInterval / checkInterval) == 0:
		saveSQL()
	# Nur updaten wenn update_interval verstrichen ist
	if ticks % (update_interval / checkInterval) != 0:
		return True
	# wechselrichter nicht erreichbar -> limit kann eh nicht gesetzt werden -> skip
	if not inverterIsReachable:
		if inverterWasReachable:
			inverterWasReachable = False
			log(f'Wechselrichter nicht erreichbar. Skippe Logs bis wieder erreichbar.')
		return False
	# Wechselrichter ist erreichbar
	if not inverterWasReachable:
		log(f'Wechselrichter wieder erreichbar. Führe Skript normal weiter.')
		inverterWasReachable = True
	# Wechselrichter gibt nicht old_limit_a Watt aus, sondern weniger, außer das limit ist 0.
	if current_power_delivery > 0 and old_limit_a > 0:
		limit_ratio = old_limit_a / current_power_delivery
	else:
		limit_ratio = 1
	if batteryIsOn:
		if batteryWasOff:
			log(f'Batterie ist wieder an. Führe Skript normal weiter.')
			batteryWasOff = False
		# Unter grenze -> Limits auf 0
		if battery_voltage < battery_voltage_threshold: 
			if batteryWasBelowThreshold:
				return False
			batteryWasBelowThreshold = True
			log(f'Batteriespannung ist {battery_voltage}V, was niedriger als die festgelegte Grenze {battery_voltage_threshold}V ist.')
			log(f'Limit wird bis Sonnenaufgang ({sunrise.time()}) auf 0 gesetzt.')
			new_limit_a = 0
		# batterie an + gute spannung -> Berechne limit
		else:
			if batteryWasBelowThreshold:
				log(f'Batteriespannung wieder über Grenze. Skript wird fortgeführt.')
				batteryWasBelowThreshold = False
			new_limit_a = round(limit_ratio * (current_power_consumption + current_power_delivery)) # works even if negative.
	else:
		if batteryWasOff: # Batterie war bereits aus -> skip
			return True
		batteryWasOff = True
		if solarIsOn:
			log(f'Batterie ist aus, Solarpanele liefern Strom. Setze Limit auf 100 und warte.')
			new_limit_a = max_power
		else:
			log(f'Batterie ist aus, Solarpanele liefern keinen Strom. Setze Limit auf 0 und warte.')
			new_limit_a = 0
	new_limit_a = max(0, min(max_power, new_limit_a)) # clamp between 0%, 100%
	new_limit_r = round(100 * new_limit_a / max_power, ndigits=1)
	log(f'Aktueller Stromverbrauch:\t{Fore.LIGHTRED_EX if current_power_consumption >= 0 else Fore.LIGHTGREEN_EX}{current_power_consumption}W')
	log(f'Aktuelles Limit: {Fore.LIGHTWHITE_EX}{old_limit_r}% / {old_limit_a}W{Style.RESET_ALL}. Gesamtleistung: {Fore.LIGHTCYAN_EX}{current_power_delivery}W.')
	if (new_limit_a != old_limit_a):
		# wechselrichter beschäftigt -> skip
		if limit_set_status == "Pending":
			log(f'Neues Limit wäre {Fore.LIGHTCYAN_EX}{new_limit_r}% / {new_limit_a}W{Style.RESET_ALL}, aber Wechselrichter verarbeitet noch das vorherige Limit. Skippe.')
			return True
		log(f'Neues Limit: {Fore.LIGHTCYAN_EX}{new_limit_r}% / {new_limit_a}W{Style.RESET_ALL} ({round(new_limit_a/limit_ratio)} = {current_power_consumption} + {current_power_delivery})')
		setLimitResponse = dtu.inverterSetLimitConfig(main_inverter, {"limit_type":0, "limit_value":new_limit_a})
		limitWasUnchanged = False
		if (setLimitResponse['type'] != "success"):
			log(f'{Back.LIGHTRED_EX}{Fore.BLACK}Fehler{Style.RESET_ALL} beim setzen des Limits. Fehlernachricht: {setLimitResponse}')
	elif not limitWasUnchanged:
		log(f'Neues und altes Limit gleich, kein Update erforderlich.')
		limitWasUnchanged = True
	return True

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
			print(f"{Back.LIGHTRED_EX}{Fore.BLACK}Warnung{Style.RESET_ALL}: Skript hängt {round(abs(sleep_time),ndigits=1)}s hinter Checks!")
except KeyboardInterrupt:
	log(f'Benutzerunterbrechung. Schließe...')
	exit()