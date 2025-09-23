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
update_interval = 2000 # Time in milliseconds between each update
checkInterval = 250 # Time in milliseconds between each check
logInTextFile = True # Enable if you want all console output to be logged
storeData = True # Whether to store received data in SQL
battery_voltage_threshold = 48.5 # Threshold below which connection with battery is stopped.
saveInterval = 5 # Time in seconds between each write to database
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

def saveSQL(inverterLimit: float, batteryPower: float, powerConsumption: float, voltage: float):
	timestamp = int(time.time())
	try:
		cursor.execute("""
			INSERT INTO measurements (timestamp, inverterLimit, battery, consumption, voltage)
			VALUES (?, ?, ?, ?, ?)
		""", (timestamp, inverterLimit, batteryPower, powerConsumption, voltage))
		conn.commit()
	except sqlite3.Error as e:
		log(f'{Back.LIGHTRED_EX}{Fore.BLACK}Speichern fehlgeschlagen: {e}')


log(f'Programmstart: [{(datetime.now()).strftime("%Y-%m-%d %H:%M:%S")}]')
log(f'Sonnenaufgang: {sunrise.time()}, Sonnenuntergang: {sunset.time()}')


dtu = openDTU(urlOpenDTU, portOpenDTU, username, password)
ticks = 1
inverterWasReachable = True
limitWasUnchanged = False
batteryWasBelowThreshold = False
batteryWasOn = True
main_inverter = False


log(f'Starte..')


def update():
	global ticks, inverterWasReachable, limitWasUnchanged, batteryWasBelowThreshold, batteryWasOn, main_inverter
	ticks += 1
	try:
		if not main_inverter:
			main_inverter = dtu.inverterGetSerial(0)
		inverter_limit_config = dtu.inverterGetLimitConfig()
		inverter_runtime_info = dtu.inverterGetRuntimeInfo(main_inverter)
		inverterIsReachable = inverter_runtime_info['inverters'][0]['reachable']
		# flagProducing = inverter_runtime_info['inverters'][0]['producing']
		for index in inverter_runtime_info['inverters'][0]['DC']:
			if "batterie" in inverter_runtime_info['inverters'][0]['DC'][index]['name']['u'].lower():
				battery_power = inverter_runtime_info['inverters'][0]['DC'][index]['Power']['v']
				battery_voltage = inverter_runtime_info['inverters'][0]['DC'][index]['Voltage']['v']
		batteryIsOn = True if battery_power > 0 else False
		old_limit_r = float(inverter_runtime_info['inverters'][0]['limit_relative'])
		old_limit_a = round(inverter_runtime_info['inverters'][0]['limit_absolute'])
		# current_dc_power_delivery = inverter_runtime_info['inverters'][0]['INV']['0']['Power DC']['v']
		# ac_dc_conversion_ratio = inverter_runtime_info['inverters'][0]['INV']['0']['Efficiency']['v'] / 100
		current_power_delivery = inverter_runtime_info['total']['Power']['v']
		max_power = inverter_limit_config[main_inverter]['max_power']
		limit_set_status = inverter_limit_config[main_inverter]['limit_set_status']
	except BaseException as e:
		if type(e) == KeyboardInterrupt:
			raise
		log(f"{Back.LIGHTRED_EX}{Fore.BLACK}Fehler{Style.RESET_ALL} bei der Datenabfrage von openDTU.")
		return False
	
	try:
		bitMeter_data = requests.get(url = f'{urlBitshake}/cm?cmnd=status 10').json()
		current_power_consumption = bitMeter_data["StatusSNS"]["LK13BE"]["Power"]
		current_power_consumption = max(-5000, min(30000, current_power_consumption)) # data between -5000 and 30000
	except BaseException as e:
		if type(e) == KeyboardInterrupt:
			raise
		log(f'{Back.LIGHTRED_EX}{Fore.BLACK}Fehler{Style.RESET_ALL} bei Datenabfrage von BitMeter.')
		return False
	
	if storeData and ticks % (1000 * saveInterval / checkInterval) == 0:
		saveSQL(old_limit_a, current_power_delivery, current_power_consumption, battery_voltage)
	
	if ticks % (update_interval / checkInterval) == 0:
		if not inverterIsReachable:
			if inverterWasReachable:
				inverterWasReachable = inverterIsReachable
				log(f'Wechselrichter nicht erreichbar. Skippe Logs bis wieder erreichbar.')
			else:
				return False
		elif limit_set_status == "Pending":
			log(f'Wechselrichter verarbeitet noch das vorherige Limit. Skippe.')
		else:
			if not inverterWasReachable:
				log(f'Wechselrichter wieder erreichbar. Führe Skript normal weiter.')
			inverterWasReachable = inverterIsReachable
			if current_power_delivery > 0 and old_limit_a > 0: # no division by 0
				limit_ratio = old_limit_a / current_power_delivery
			else:
				limit_ratio = 1

			if batteryIsOn: # if battery is on, we adjust the limit to have net zero input into electricity grid
				if not batteryWasOn:
					log(f'Batterie liefert ab jetzt Strom. Beginne mit Anpassung des Limits.')
					batteryWasOn = True
				if battery_voltage < battery_voltage_threshold: # if we fall below threshold, set limit to 0 and wait
					if batteryWasBelowThreshold:
						return False
					log(f'Batteriestrom ist {battery_voltage}V, was niedriger als die festgelegte Grenze {battery_voltage_threshold}V ist.')
					log(f'Limit wird bis Sonnenaufgang ({sunrise.time()}) auf 0 gesetzt.')
					batteryWasBelowThreshold = True
					new_limit_a = 0
					new_limit_r = 0
				else:
					if batteryWasBelowThreshold:
						log(f'Batterie liefert wieder Strom. Skript wird fortgeführt.')
					new_limit_a = round(limit_ratio * (current_power_consumption + current_power_delivery)) # works even if negative.
					new_limit_r = round(100 * new_limit_a / max_power, ndigits=1)
					batteryWasBelowThreshold = False
			else: # if battery is off, we set the limit to 100 once and don't do anything after that.
				if not batteryWasOn:
					return True
				if old_limit_r != 100 or ticks * checkInterval // update_interval == 1:
					log(f'Batterie liefert keinen Strom. Setze Limit auf 100 und warte.')
					new_limit_r = 0 # 100
					new_limit_a = 0 # max_power
					batteryWasOn = False
			# adjust limits so that they stay between 0-100%
			if new_limit_a > max_power:
				new_limit_a = max_power
				new_limit_r = 100
			elif new_limit_a  < 0:
				new_limit_a = 0
				new_limit_r = 0
			log(f'Aktueller Stromverbrauch:\t{Fore.LIGHTRED_EX if current_power_consumption >= 0 else Fore.LIGHTGREEN_EX}{current_power_consumption}W')
			log(f'Aktuelles Limit: {Fore.LIGHTWHITE_EX}{old_limit_r}% / {old_limit_a}W{Style.RESET_ALL}. Gesamtleistung: {Fore.LIGHTCYAN_EX}{current_power_delivery}W.')
			if (new_limit_a != old_limit_a):
				log(f'Neues Limit: {Fore.LIGHTCYAN_EX}{new_limit_r}% / {new_limit_a}W{Style.RESET_ALL} ({round(new_limit_a/limit_ratio)} = {current_power_consumption} + {current_power_delivery})')
				setLimitResponse = dtu.inverterSetLimitConfig(main_inverter, {"limit_type":0, "limit_value":new_limit_a})
				limitWasUnchanged = False
				if (setLimitResponse['type'] != "success"):
					log(f'{Back.LIGHTRED_EX}{Fore.BLACK}Fehler{Style.RESET_ALL} beim setzen des Limits. Fehlernachricht: {setLimitResponse}')
			elif not limitWasUnchanged:
				log(f'Neues und altes Limit gleich, kein Update erforderlich.')
				limitWasUnchanged = True
	return True

while True:
	if update():
		time.sleep(checkInterval / 1000)
	else:
		time.sleep(checkInterval / 250)