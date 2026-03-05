from enum import Enum, auto
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
battery_voltage_threshold = 48.5 # Threshold below which connection with battery is stopped.
battery_voltage_thresholds = [51, 50, 50, 49]
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

class LogStyle(Enum):
	DEFAULT = auto()
	WARNING = auto()
	INFO = auto()
	ERROR = auto()
	
def log(text, style=LogStyle.DEFAULT):
	fdate = datetime.now().strftime("%H:%M:%S")
	timestamp = f'{Fore.LIGHTYELLOW_EX}[{fdate}]{Style.RESET_ALL}'
	formats = {
		LogStyle.DEFAULT: f'{text}',
		LogStyle.WARNING: f'{Back.LIGHTRED_EX}{Fore.BLACK}[WARNING]{Style.RESET_ALL} {text}',
		LogStyle.INFO: f'{Back.LIGHTYELLOW_EX}{Fore.BLACK}[INFO]{Style.RESET_ALL} {text}',
		LogStyle.ERROR: f'{Back.LIGHTRED_EX}{Fore.BLACK}[ERROR]{text}{Style.RESET_ALL}'
	}
	logLine = timestamp + ' ' + formats.get(style, LogStyle.DEFAULT) + Style.RESET_ALL
	print(logLine)
	if logInTextFile:
		fName = getFileName() + '_log.txt'
		try:
			with open(fName, "a+") as f:
				clean_text = re.sub(r'\x1b\[[0-9;]*[mGKH]', '', logLine)
				f.write(clean_text + '\n')
		except Exception as e:
			print(f'{timestamp} {Back.LIGHTRED_EX}{Fore.BLACK}ERROR: FAILED TO WRITE TO LOG FILE.{Style.RESET_ALL}')

def getFileName():
	return f'{(datetime.now()).strftime("%Y-%m-%d")}'

def saveSQL():
	global data_timestamps, data_oldLimits, data_powerDelivery, data_powerConsumption, data_batteryVoltage
	rows = list(zip(data_timestamps, data_oldLimits, data_powerDelivery, data_powerConsumption, data_batteryVoltage))
	if not rows:
		return
	data_timestamps, data_oldLimits, data_powerDelivery, data_powerConsumption, data_batteryVoltage = [], [], [], [], []
	try:
		cursor.executemany("""
			INSERT OR IGNORE INTO measurements (timestamp, inverterLimit, battery, consumption, voltage)
			VALUES (?, ?, ?, ?, ?)
		""", rows)
		conn.commit()
	except sqlite3.Error as e:
		log(f'Speichern fehlgeschlagen: {e}', style=LogStyle.ERROR)


log(f'Program Start: [{(datetime.now()).strftime("%Y-%m-%d %H:%M:%S")}]')
log(f'Sunrise: {sunrise.time()}, Sunset: {sunset.time()}')

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
power_consumption_last_tick = 0
power_consumption_last_tick2 = 0
data_timestamps, data_oldLimits, data_powerDelivery, data_powerConsumption, data_batteryVoltage = [], [], [], [], []

log(f'Starting..')

def update():
	global ticks, main_inverter, inverterWasReachable, limitWasUnchanged, batteryWasBelowThreshold, batteryWasOff, last_save_time, power_consumption_last_tick, power_consumption_last_tick2
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
		if max_power == 0:
			raise ValueError('DTU returned inverter limit config with max_power = 0')
		limit_set_status = inverter_limit_config[main_inverter]['limit_set_status']
	except BaseException as e:
		if type(e) == KeyboardInterrupt:
			raise
		log(f"Could not parse data from openDTU: {e}", LogStyle.ERROR)
		return False
	
	try:
		bitMeter_data = requests.get(url = f'{urlBitshake}/cm?cmnd=status 10').json()
		power_consumption_now = bitMeter_data["StatusSNS"]["LK13BE"]["Power"]
		# remove unrealistic consumption erroneously reported by the bitshake reader
		if power_consumption_now > 50000:
			power_consumption_now = power_consumption_last_tick
		# update sliding window
		power_consumption_last_tick2_copy = power_consumption_last_tick2
		power_consumption_last_tick_copy = power_consumption_last_tick
		power_consumption_last_tick2 = power_consumption_last_tick
		power_consumption_last_tick = power_consumption_now
		# remove single spikers erroneously reported by the bitshake reader
		# if values are incoming 550, 123, 200, 500, 10000 
		# -> 10000 - 500 > 5000 CHECK
		# -> 500 - 200 NOT > 5000 CHECK so correct that 10000 to 500. -> 550, 123, 200, 500, 500 
		# then, if the next number is 11000
		# -> 11000 - 10000 NOT > 5000 so first if check fails, the number goes through -> 550, 123, 200, 500, 500, 11000
		# if the next number is 666 (so low again)
		# -> abs(666 - 10000) > 5000 CHECK
		# -> 10000 - 666 > 5000 NOPE so second if check FAILS, no correction is made and 500 goes through -> 550, 123, 200, 500, 500, 666: spike removed
		# if the next number is >10k again, we have a problem. but its fine
		if abs(power_consumption_now - power_consumption_last_tick_copy) > 10000:
			if not abs(power_consumption_last_tick2_copy - power_consumption_last_tick_copy) > 10000: 
				power_consumption_now = power_consumption_last_tick_copy
	except BaseException as e:
		if type(e) == KeyboardInterrupt:
			raise
		log(f"Could not parse data from bitMeter: {e}", LogStyle.ERROR)
		return False
	if storeData and last_save_time != now: # store data every second
		data_timestamps.append(now)
		data_oldLimits.append(old_limit_a)
		data_powerDelivery.append(current_power_delivery)
		data_powerConsumption.append(power_consumption_now)
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
			if batteryWasOff and not batteryIsOn:
				log("No connection to inverter. Battery was and is offline, so no actions necessary.", LogStyle.INFO)
			else:
				log('No connection to inverter. Battery was on, so this is unusual. Skipping logs until reachable.', LogStyle.INFO)
		return False
	# Wechselrichter ist erreichbar
	if not inverterWasReachable:
		inverterWasReachable = True
		if batteryWasOff and not batteryIsOn:
			log("Reestablished connection to inverter. Battery is still off, continue waiting.", LogStyle.INFO)
		else:
			log('Reestablished connection to inverter. Continuing script.', LogStyle.INFO)
	# Wechselrichter gibt nicht old_limit_a Watt aus, sondern weniger, außer das limit ist 0.
	if current_power_delivery > 0 and old_limit_a > 0:
		limit_ratio = old_limit_a / current_power_delivery
	else:
		limit_ratio = 1
	if batteryIsOn:
		if batteryWasOff:
			log('Battery is delivering electricity again. Continuing script.', LogStyle.INFO)
			batteryWasOff = False
		# Unter grenze -> Limits auf 0
		if battery_voltage < battery_voltage_threshold: 
			if batteryWasBelowThreshold:
				return False
			batteryWasBelowThreshold = True
			log(f'Battery voltage is {battery_voltage}V, which is below the set limit {battery_voltage_threshold}V.', LogStyle.INFO)
			log(f'Setting Limit to 0 until Sunrise ({sunrise.time()}).', LogStyle.INFO)
			new_limit_a = 0
		# batterie an + gute spannung -> Berechne limit
		else:
			if batteryWasBelowThreshold:
				log('Battery voltage is above threshold again. Continuing Script.', LogStyle.INFO)
				batteryWasBelowThreshold = False
			new_limit_a = round(limit_ratio * (power_consumption_now + current_power_delivery)) # works even if negative.
	else:
		if batteryWasOff: # Batterie war bereits aus -> skip
			return True
		batteryWasOff = True
		if solarIsOn:
			log('Battery is off, solar panels are delivering power. Setting Limit to 100 and sleep.', LogStyle.INFO)
			new_limit_a = max_power
		else:
			log('Battery is off, solar panels are not delivering power. Setting Limit to 0 and sleep.', LogStyle.INFO)
			new_limit_a = 0
	new_limit_a = max(0, min(max_power, new_limit_a)) # clamp between 0%, 100%
	new_limit_r = round(100 * new_limit_a / max_power, ndigits=1)
	log(f'Current Power Consumption:\t{Fore.LIGHTRED_EX if power_consumption_now >= 0 else Fore.LIGHTGREEN_EX}{power_consumption_now}W')
	log(f'Current Limit: {Fore.LIGHTWHITE_EX}{old_limit_r}% / {old_limit_a}W{Style.RESET_ALL}. Total Power: {Fore.LIGHTCYAN_EX}{current_power_delivery}W.')
	if (new_limit_a != old_limit_a):
		# wechselrichter beschäftigt -> skip
		if limit_set_status == "Pending":
			log(f'New Limit would be {Fore.LIGHTCYAN_EX}{new_limit_r}% / {new_limit_a}W{Style.RESET_ALL}, but inverter is busy. Skipping.', LogStyle.WARNING)
			return True
		log(f'New Limit: {Fore.LIGHTCYAN_EX}{new_limit_r}% / {new_limit_a}W{Style.RESET_ALL} ({round(new_limit_a/limit_ratio)} = {power_consumption_now} + {current_power_delivery})')
		setLimitResponse = dtu.inverterSetLimitConfig(main_inverter, {"limit_type":0, "limit_value":new_limit_a})
		limitWasUnchanged = False
		if (setLimitResponse['type'] != "success"):
			log(f'Could not set inverter limit: {setLimitResponse}', LogStyle.ERROR)
	elif not limitWasUnchanged:
		log("Current and new Limit match, no update necessary.")
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
			log(f"Script is {round(abs(sleep_time),ndigits=1)} seconds behind!", LogStyle.WARNING)
except KeyboardInterrupt:
	log('User Interruption. Closing...', LogStyle.INFO)