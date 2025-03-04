import time, json
from openDTU import openDTU
from termcolor import colored

# Initialize the openDTU instance
url = "http://192.168.178.48"
port = 80
# store the password in a file, otherwise directly add it here
username = "admin"
password = open(r"C:\Users\Simon\Desktop\programs\Files\openDTUAuth.pw").read().strip()

dtu = openDTU(url, port, username, password)
serial = dtu.inverterGetSerial()
# List of functions to test
functions_to_test = [
	# ("inverterGetList", dtu.inverterGetList),
	# ("inverterGetRuntimeInfo", lambda: dtu.inverterGetRuntimeInfo(serial)),
	# ("inverterGetDevinfo", dtu.inverterGetDevinfo),
	# ("inverterGetEventlog", lambda: dtu.inverterGetEventlog(serial)),
	# ("inverterGetGridProfile", lambda: dtu.inverterGetGridProfile(serial)),
	# ("inverterGetGridProfileRawData", lambda: dtu.inverterGetGridProfileRawData(serial)),
	# ("inverterGetLimitConfig", dtu.inverterGetLimitConfig),
	# ("inverterGetPowerConfig", dtu.inverterGetPowerConfig),
	# ("systemGetStatus", dtu.systemGetStatus),
	# ("prometheusGetMetrics", dtu.prometheusGetMetrics),
	# ("dtuGetConfig", dtu.dtuGetConfig),
	# ("mqttGetStatus", dtu.mqttGetStatus),
	# ("mqttGetConfig", dtu.mqttGetConfig),
	# ("ntpGetStatus", dtu.ntpGetStatus),
	# ("ntpGetConfig", dtu.ntpGetConfig),
	("ntpGetTime", dtu.ntpGetTime),
	("networkGetStatus", dtu.networkGetStatus),
	("networkGetConfig", dtu.networkGetConfig),
	("deviceGetConfig", dtu.deviceGetConfig),
	("securityGetConfig", dtu.securityGetConfig),
	("securityAuthenticate", dtu.securityAuthenticate),
]

# Run tests
for func_name, func in functions_to_test:
	print(colored(f"Testing {func_name}...", 'blue', attrs=['bold']))
	time.sleep(1)
	try:
		result = func()
		print(colored(f"Result: {result}"))
	except Exception as e:
		print(f"Error: {e}")
	input(colored("Press Enter to continue to the next test...", 'red', attrs=['bold']))