from openDTU import *
import json
username = "admin"
password = open(r"C:\Users\Simon\Desktop\programs\Files\openDTUAuth.pw").read().strip()
urlOpenDTU = "http://192.168.178.48"
port = 80

dtu = openDTU(urlOpenDTU, port, username, password)
main_inverter = dtu.inverterGetSerial(0)

# setLimitResponse = dtu.inverterSetLimitConfig(main_inverter, {"limit_type":1, "limit_value":50})
inverter_runtime_info = dtu.inverterGetRuntimeInfo(main_inverter)
# print(json.dumps(inverter_runtime_info))

battery_power = inverter_runtime_info['inverters'][0]['DC']
for channel in battery_power:
	if battery_power[channel]['name']['u'] == 'Batterie-Lader':
		print(f"{battery_power[channel]['name']['u']}")
