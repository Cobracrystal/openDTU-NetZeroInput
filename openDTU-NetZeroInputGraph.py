import time
from datetime import datetime
import suntime
from openDTU import * 
from dateutil import tz
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import matplotlib.dates as mdates

username = "admin"
password = open(r"C:\Users\Simon\Desktop\programs\Files\openDTUAuth.pw").read().strip()
urlOpenDTU = "http://192.168.178.48"
urlBitshake = "http://192.168.178.40"
port = 80
latitude = 50.988768
longitude = 7.190650
standard_interval = 5 # Time in seconds between each check
flag_create_graph = True


###### TODO : CHECK IF SUNRISE/SUNSET, OPERATE BASED ON THAT. 


sun = suntime.Sun(lat=latitude, lon=longitude)
sunset = sun.get_sunset_time(time_zone=tz.gettz("Europe/Berlin"))
sunrise = sun.get_sunrise_time(time_zone=tz.gettz("Europe/Berlin"))

print(f'Programmstart: Sonnenaufgang ist um {sunrise.time()} und Untergang um {sunset.time()}')

dtu = openDTU(urlOpenDTU, port, username, password)

main_inverter = dtu.inverterGetSerial(0)
max_power = dtu.inverterGetLimitConfig()[main_inverter]['max_power']

graphTime, graphBatteryPower, graphPowerConsumption, graphPowerLimit = [], [], [], []
figure, axes = plt.subplots()
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
line0, = plt.plot(graphTime, graphBatteryPower, 'r')
line1, = plt.plot(graphTime, graphPowerConsumption, 'g')
line2, = plt.plot(graphTime, graphPowerLimit, 'b')
figure.autofmt_xdate()
axes.set_ylim(-100, max_power)

def init():
	axes.set_ylim(-100, max_power)
	figure.autofmt_xdate()
	line0.set_data(graphTime, graphBatteryPower)
	line1.set_data(graphTime, graphPowerConsumption)
	line2.set_data(graphTime, graphPowerLimit)
	return line0, line1, line2

def update(frame):
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
		print(f'Error has occured while trying to get openDTU data. Waiting 1 minute before retrying. Exception: {repr(e)}')
		time.sleep(60)
		return line0, line1, line2,
	
	try:
		bitMeter_data = requests.get(url = f'{urlBitshake}/cm?cmnd=status 10').json()
		current_power_consumption = bitMeter_data["StatusSNS"]["LK13BE"]["Power"]
	except Exception as e:
		print(f'Error has occured while trying to get BitMeter data. Waiting 1 minute before retrying. Exception: {repr(e)}')
		time.sleep(60)
		return line0, line1, line2,
	
	if limit_set_status != 'Ok': # If previous change of limit has not been finalized, wait and retry.
		print(f'Inverter Limit Status is currently {limit_set_status}. Waiting 10 seconds before retrying.')
		time.sleep(10)
		return line0, line1, line2,

	if not flagReachable:
		print(f'Inverter is not reachable')
		time.sleep(600)
		return line0, line1, line2,

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
	print(f'Aktueller Stromverbrauch:\t{current_power_consumption}W')
	print(f'Altes Limit: {old_limit_r}% / {old_limit_a}W. Batterieleistung: {current_power_delivery}W.')
	print(f'Neues Limit: {new_limit_r}% / {new_limit_a}W ({new_limit_a}/4 = {new_limit_a//4}, {current_power_consumption + current_power_delivery} = {current_power_consumption} + {current_power_delivery})')
	setLimitResponse = dtu.inverterSetLimitConfig(main_inverter, {"limit_type":0, "limit_value":new_limit_a})
	if (setLimitResponse['type'] != "success"):
		print(f'Error when setting new Limit. Error message: {setLimitResponse}')
	graphTime.append(datetime.now())
	graphBatteryPower.append(current_power_delivery)
	graphPowerConsumption.append(current_power_consumption)
	graphPowerLimit.append(old_limit_a)
	line0.set_data(graphTime, graphBatteryPower)
	line1.set_data(graphTime, graphPowerConsumption)
	line2.set_data(graphTime, graphPowerLimit)
	figure.gca().relim()
	figure.gca().autoscale_view()
	return line0, line1, line2,

try:
	animation = FuncAnimation(figure, update, blit=False, init_func=init, cache_frame_data=False, interval=standard_interval * 1000)
	plt.show()
except KeyboardInterrupt:
	print(f"Programm wird geschlossen. Setze Limit auf 60%...")
	if dtu.inverterSetLimitConfig(main_inverter, {"limit_type":1, "limit_value":60})['type'] == "Success":
		print(f"Limit auf 60% gesetzt. Beende..")
	else:
		print(f"Limit wurde nicht gesetzt. Beende..")