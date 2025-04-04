import time
import suntime
from openDTU import * 
from dateutil import tz

username = "admin"
password = open(r"C:\Users\Simon\Desktop\programs\Files\openDTUAuth.pw").read().strip()
urlOpenDTU = "http://192.168.178.48"
urlBitshake = "http://192.168.178.40"
port = 80
latitude = 50.988768
longitude = 7.190650
standard_interval = 10 # Time in seconds between each check


###### TODO : CHECK IF SUNRISE/SUNSET, OPERATE BASED ON THAT. 
######  TODO: GENERATE GRAPH OF BATTERY DRAIN, LIMITS AND POWER


sun = suntime.Sun(lat=latitude, lon=longitude)
sunset = sun.get_sunset_time(time_zone=tz.gettz("Europe/Berlin"))
sunrise = sun.get_sunrise_time(time_zone=tz.gettz("Europe/Berlin"))

print(f'Programmstart: Sonnenaufgang ist um {sunrise.time()} und Untergang um {sunset.time()}')

dtu = openDTU(urlOpenDTU, port, username, password)

main_inverter = dtu.inverterGetSerial(0)
max_power = dtu.inverterGetLimitConfig()[main_inverter]['max_power']

while(True):
	try:
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
			continue
		
		try:
			bitMeter_data = requests.get(url = f'{urlBitshake}/cm?cmnd=status 10').json()
			current_power_consumption = bitMeter_data["StatusSNS"]["LK13BE"]["Power"]
		except Exception as e:
			print(f'Error has occured while trying to get BitMeter data. Waiting 1 minute before retrying. Exception: {repr(e)}')
			time.sleep(60)
			continue
		
		if limit_set_status != 'Ok': # If previous change of limit has not been finalized, wait and retry.
			print(f'Inverter Limit Status is currently {limit_set_status}. Waiting 10 seconds before retrying.')
			time.sleep(10)
			continue
		if not flagReachable:
			print(f'Inverter is not reachable')
			time.sleep(600)
			continue
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
		time.sleep(standard_interval)
	except KeyboardInterrupt:
		# print("Programm wird geschlossen. Setze Limit auf 60%")
		# dtu.inverterSetLimitConfig(main_inverter, {"limit_type":1, "limit_value":60})
		break
