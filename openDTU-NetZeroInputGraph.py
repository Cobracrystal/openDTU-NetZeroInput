import time
import suntime
from datetime import datetime, timedelta
from openDTU import * 
from dateutil import tz
from matplotlib import dates, pyplot as plt
from matplotlib.animation import FuncAnimation

username = "admin"
password = open(r"C:\Users\Simon\Desktop\programs\Files\openDTUAuth.pw").read().strip()
urlOpenDTU = "http://192.168.178.48"
urlBitshake = "http://192.168.178.40"
port = 80
latitude = 50.988768
longitude = 7.190650
standard_interval = 1 # Time in seconds between each check
max_graph_width = 10000 # Number of datapoints the graph should keep.

###### TODO : CHECK IF SUNRISE/SUNSET, OPERATE BASED ON THAT. 
###### TODO : dtu: 37.6, internal: 39.1 VOLT. SHUTDOWN BEFORE THAT.

sun = suntime.Sun(lat=latitude, lon=longitude)
sunset = sun.get_sunset_time(time_zone=tz.gettz("Europe/Berlin"))
sunrise = sun.get_sunrise_time(time_zone=tz.gettz("Europe/Berlin"))

print(f'Programmstart: Sonnenaufgang ist um {sunrise.time()} und Untergang um {sunset.time()}')

dtu = openDTU(urlOpenDTU, port, username, password)

main_inverter = dtu.inverterGetSerial(0)
max_power = dtu.inverterGetLimitConfig()[main_inverter]['max_power']

graphTime, graphBatteryPower, graphPowerConsumption, graphPowerLimit = [], [], [], []
figure, axes = plt.subplots(num='Leistung')
plt.gca().xaxis.set_major_formatter(dates.DateFormatter("%H:%M:%S"))
line0, = plt.plot(graphTime, graphBatteryPower, 'g', label='Batterieleistung')
line1, = plt.plot(graphTime, graphPowerConsumption, 'r', label='Stromverbrauch')
line2, = plt.plot(graphTime, graphPowerLimit, 'b', label='Wechselrichterlimit')

def init():
	axes.set_ylim(-100, max_power)
	figure.autofmt_xdate()
	figure.tight_layout()
	plt.ylabel("Leistung")
	plt.legend()
	line0.set_data(graphTime, graphBatteryPower)
	line1.set_data(graphTime, graphPowerConsumption)
	line2.set_data(graphTime, graphPowerLimit)
	return line0, line1, line2

def update(frame):
	try:
		update.ticks += 1
	except:
		update.ticks = 1
		update.wasReachable = True
	try:
		inverter_limit_config = dtu.inverterGetLimitConfig()
		inverter_runtime_info = dtu.inverterGetRuntimeInfo()
		flagReachable = inverter_runtime_info['inverters'][0]['reachable']
		flagProducing = inverter_runtime_info['inverters'][0]['producing']
		old_limit_r = inverter_runtime_info['inverters'][0]['limit_relative']
		old_limit_a = inverter_runtime_info['inverters'][0]['limit_absolute']
		current_power_delivery = inverter_runtime_info['total']['Power']['v']
		limit_set_status = inverter_limit_config[main_inverter]['limit_set_status']
	except Exception as e:
		print(f'[{datetime.now().strftime("%H:%M:%S")}] Fehler bei Datenabfrage von openDTU. Warte eine Minute vor nächstem Versuch. Fehlernachricht: {repr(e)}')
		time.sleep(60)
		return line0, line1, line2,
	
	try:
		bitMeter_data = requests.get(url = f'{urlBitshake}/cm?cmnd=status 10').json()
		current_power_consumption = bitMeter_data["StatusSNS"]["LK13BE"]["Power"]
	except Exception as e:
		print(f'[{datetime.now().strftime("%H:%M:%S")}] Fehler bei Datenabfrage von BitMeter. Warte eine Minute vor nächstem Versuch. Fehlernachricht: {repr(e)}')
		time.sleep(60)
		return line0, line1, line2,
	
	if not flagReachable:
		if update.wasReachable:
			print(f'[{datetime.now().strftime("%H:%M:%S")}] Wechselrichter nicht erreichbar. Skippe Logs bis wieder erreichbar.')
	elif limit_set_status == "Pending":
		print(f'[{datetime.now().strftime("%H:%M:%S")}] Wechselrichter verarbeitet noch das vorherige Limit. Skippe.')
	else:
		old_limit_a = round(old_limit_a)
		old_limit_r = float(old_limit_r)
		old_limit_adj_a = old_limit_a // 4 
		new_limit_a = current_power_consumption + old_limit_adj_a # works even if negative.
		new_limit_a = new_limit_a * 4
		new_limit_r = round(100 * new_limit_a / max_power, ndigits=1)
		if new_limit_a > max_power:
			new_limit_a = max_power
			new_limit_r = 100
		elif new_limit_a  < 0:
			new_limit_a = 0
			new_limit_r = 0
		print(f'[{datetime.now().strftime("%H:%M:%S")}] Aktueller Stromverbrauch:\t{current_power_consumption}W')
		print(f'[{datetime.now().strftime("%H:%M:%S")}] Altes Limit: {old_limit_r}% / {old_limit_a}W. Batterieleistung: {current_power_delivery}W.')
		print(f'[{datetime.now().strftime("%H:%M:%S")}] Neues Limit: {new_limit_r}% / {new_limit_a}W ({new_limit_a}/4 = {new_limit_a//4}, {current_power_consumption + current_power_delivery} = {current_power_consumption} + {current_power_delivery})')
		setLimitResponse = dtu.inverterSetLimitConfig(main_inverter, {"limit_type":0, "limit_value":new_limit_a})
		if (setLimitResponse['type'] != "success"):
			print(f'[{datetime.now().strftime("%H:%M:%S")}] Fehler beim setzen des Limits. Fehlernachricht: {setLimitResponse}')
	update.wasReachable = flagReachable
	graphTime.append(datetime.now())
	graphBatteryPower.append(current_power_delivery)
	graphPowerConsumption.append(current_power_consumption)
	graphPowerLimit.append(old_limit_a)
	line0.set_data(graphTime, graphBatteryPower)
	line1.set_data(graphTime, graphPowerConsumption)
	line2.set_data(graphTime, graphPowerLimit)
	axes.relim()
	axes.autoscale_view(tight=True)
	return line0, line1, line2,

try:
	animation = FuncAnimation(figure, update, blit=False, init_func=init, cache_frame_data=False, interval=standard_interval * 1000)
	init()
	plt.show()
except KeyboardInterrupt:
	print(f'[{datetime.now().strftime("%H:%M:%S")}] Programm wird geschlossen. Setze Limit auf 60%...')
	if dtu.inverterSetLimitConfig(main_inverter, {"limit_type":1, "limit_value":60})['type'] == "Success":
		print(f'[{datetime.now().strftime("%H:%M:%S")}] Limit auf 60% gesetzt. Beende..')
	else:
		print(f'[{datetime.now().strftime("%H:%M:%S")}] Limit wurde nicht gesetzt. Beende..')