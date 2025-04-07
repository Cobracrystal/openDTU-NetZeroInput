import time
import suntime
from datetime import datetime, timedelta
from openDTU import *
from dateutil import tz
from matplotlib import dates, pyplot as plt
from matplotlib.animation import FuncAnimation
import pickle

username = "admin"
password = open(r"C:\Users\Simon\Desktop\programs\Files\openDTUAuth.pw").read().strip()
urlOpenDTU = "http://192.168.178.48"
urlBitshake = "http://192.168.178.40"
portOpenDTU = 80
latitude = 50.988768 # for calculating sunrise/sunset
longitude = 7.190650 # for calculating sunrise/sunset
update_interval = 2000 # Time in milliseconds between each update
checkInterval = 250 # Time in milliseconds between each check
max_graph_width = 10000 # Number of datapoints the graph should keep.
flagOnlyPlot = False # Enable if you only want to see the plot, without changing the limit
flagLogInTextFile = False # Enable if you want all console output to be logged
battery_voltage_threshold = 36.5 # Threshold below which connection with battery is stopped.

###### TODO : CHECK IF SUNRISE/SUNSET, OPERATE BASED ON THAT. 

def log(str):
	fdate = datetime.now().strftime("%H:%M:%S")
	print(f'[{fdate}] {str}')
	if flagLogInTextFile:
		try:
			f = open("dtulog.txt", "a+")
			f.write(f'[{fdate}] {str}' + '\n')
		finally:
			f.close()

sun = suntime.Sun(lat=latitude, lon=longitude)
sunset = sun.get_sunset_time(time_zone=tz.gettz("Europe/Berlin"))
sunrise = sun.get_sunrise_time(time_zone=tz.gettz("Europe/Berlin"))

log(f'Programmstart: Sonnenaufgang ist um {sunrise.time()} und Untergang um {sunset.time()}')

dtu = openDTU(urlOpenDTU, portOpenDTU, username, password)

main_inverter = dtu.inverterGetSerial(0)
max_power = dtu.inverterGetLimitConfig()[main_inverter]['max_power']

figure, axes = plt.subplots(num='Leistung')
try:
	graphTime, graphPowerLimit, graphBatteryPower, graphPowerConsumption = pickle.load(open(f'data-{(datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d")}.pickle', "rb"))
	log(f'Lade Graphendaten..')
except:
	graphTime, graphPowerLimit, graphBatteryPower, graphPowerConsumption = [], [], [], []
	log(f'Keine alten Graphendaten gefunden. Starte leeren Graphen..')
line0, = plt.plot(graphTime, graphPowerLimit, 'b', label='Wechselrichterlimit')
line1, = plt.plot(graphTime, graphBatteryPower, 'g', label='Wechselrichterleistung')
line2, = plt.plot(graphTime, graphPowerConsumption, 'r', label='Stromverbrauch')

def init():
	# axes.set_ylim(-100, max_power)
	figure.autofmt_xdate()
	figure.tight_layout()
	plt.ylabel("Leistung")
	plt.legend()
	axes.xaxis.set_major_formatter(dates.DateFormatter("%H:%M:%S"))
	# axes.relim()
	line0.set_data(graphTime, graphPowerLimit)
	line1.set_data(graphTime, graphBatteryPower)
	line2.set_data(graphTime, graphPowerConsumption)
	return line0, line1, line2,

def saveAndExit():
	try:
		pickle.dump((graphTime, graphPowerLimit, graphBatteryPower, graphPowerConsumption), open(f'data-{(datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d")}.pickle', 'wb'))
		log(f'Speichern erfolgreich. Beende..')
	except:
		log(f'Speichern fehlgeschlagen. Beende..')	

def update(frame):
	try:
		try:
			update.ticks += 1
		except:
			update.ticks = 0
			update.wasReachable = True
			update.limitUnchanged = False
			update.batteryBelowThreshold = False
		try:
			inverter_limit_config = dtu.inverterGetLimitConfig()
			inverter_runtime_info = dtu.inverterGetRuntimeInfo(main_inverter)
			flagReachable = inverter_runtime_info['inverters'][0]['reachable']
			flagProducing = inverter_runtime_info['inverters'][0]['producing']
			for index in inverter_runtime_info['inverters'][0]['DC']:
				if "batterie" in inverter_runtime_info['inverters'][0]['DC'][index]['name']['u'].lower():
					battery_power = inverter_runtime_info['inverters'][0]['DC'][index]['Power']['v']
					battery_voltage = inverter_runtime_info['inverters'][0]['DC'][index]['Voltage']['v']
			battery_connected = True if battery_power > 0 else False
			old_limit_r = inverter_runtime_info['inverters'][0]['limit_relative']
			old_limit_a = inverter_runtime_info['inverters'][0]['limit_absolute']
			current_dc_power_delivery = inverter_runtime_info['inverters'][0]['INV']['0']['Power DC']['v']
			ac_dc_conversion_ratio = inverter_runtime_info['inverters'][0]['INV']['0']['Efficiency']['v'] / 100
			current_power_delivery = inverter_runtime_info['total']['Power']['v']
			limit_set_status = inverter_limit_config[main_inverter]['limit_set_status']
		except BaseException as e:
			if type(e) == KeyboardInterrupt:
				raise
			log(f'Fehler bei Datenabfrage von openDTU.')
			return line0, line1, line2,
		
		try:
			bitMeter_data = requests.get(url = f'{urlBitshake}/cm?cmnd=status 10').json()
			current_power_consumption = bitMeter_data["StatusSNS"]["LK13BE"]["Power"]
		except BaseException as e:
			if type(e) == KeyboardInterrupt:
				raise
			log(f'Fehler bei Datenabfrage von BitMeter.')
			return line0, line1, line2, 
		
		if not flagOnlyPlot and update.ticks % (update_interval / checkInterval) == 0:
			if not flagReachable:
				if update.wasReachable:
					log(f'Wechselrichter nicht erreichbar. Skippe Logs bis wieder erreichbar.')
			elif limit_set_status == "Pending":
				log(f'Wechselrichter verarbeitet noch das vorherige Limit. Skippe.')
			elif not update.batteryBelowThreshold:
				old_limit_a = round(old_limit_a)
				old_limit_r = float(old_limit_r)
				limit_ratio = old_limit_a / current_power_delivery if current_power_delivery > 0 and old_limit_a > 0 else 1 # if the power delivered is less than the limit, this is the adjustor
				if battery_connected and battery_voltage < battery_voltage_threshold:
					log(f'Batteriestrom ist {battery_voltage}V, was niedriger als die festgelegte Grenze {battery_voltage_threshold}V ist.')
					log(f'Limit wird bis Sonnenaufgang ({sunrise.time()}) auf 0 gesetzt.')
					update.batteryBelowThreshold = True
					new_limit_a = 0
					new_limit_r = 0
				else:
					new_limit_a = round(limit_ratio * (current_power_consumption + current_power_delivery)) # works even if negative.
					new_limit_r = round(100 * new_limit_a / max_power, ndigits=1)
				if new_limit_a > max_power:
					new_limit_a = max_power
					new_limit_r = 100
				elif new_limit_a  < 0:
					new_limit_a = 0
					new_limit_r = 0
				log(f'Aktueller Stromverbrauch:\t{current_power_consumption}W')
				log(f'Aktuelles Limit: {old_limit_r}% / {old_limit_a}W. Gesamtleistung: {current_power_delivery}W.')
				if (new_limit_a != old_limit_a):
					log(f'Neues Limit: {new_limit_r}% / {new_limit_a}W ({round(new_limit_a/limit_ratio)} = {current_power_consumption} + {current_power_delivery})')
					setLimitResponse = dtu.inverterSetLimitConfig(main_inverter, {"limit_type":0, "limit_value":new_limit_a})
					update.limitUnchanged = False
					if (setLimitResponse['type'] != "success"):
						log(f'Fehler beim setzen des Limits. Fehlernachricht: {setLimitResponse}')
				elif not update.limitUnchanged:
					log(f'Neues und altes Limit gleich, kein Update erforderlich.')
					update.limitUnchanged = True
			update.wasReachable = flagReachable
		graphTime.append(datetime.now())
		graphPowerLimit.append(old_limit_a)
		graphBatteryPower.append(current_power_delivery)
		graphPowerConsumption.append(current_power_consumption)
		line0.set_data(graphTime, graphPowerLimit)
		line1.set_data(graphTime, graphBatteryPower)
		line2.set_data(graphTime, graphPowerConsumption)
		axes.relim()
		axes.autoscale_view(tight=True)
		return line0, line1, line2,
	except KeyboardInterrupt:
		raise SystemExit

try:
	animation = FuncAnimation(figure, update, blit=True, init_func=init, cache_frame_data=False, interval=checkInterval)
	init()
	plt.show()
except KeyboardInterrupt:
	log(f'Benutzerunterbrechung...')
finally:
	saveAndExit()