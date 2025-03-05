from requests.auth import HTTPBasicAuth
import requests, json

class openDTU:
	def __init__(self, url, port = 80, username = None, password = None):
		self.name = "openDTU"
		self.version = "0.0.1"
		self.url = url
		self.port = port
		self.baseURL = f'{self.url}:{self.port}/api/'
		self.username = username
		self.password = password

	# ================ DIRECT API IMPLEMENTATIONS ================ #
	# ALL COMMENTED FUNCTIONS ARE UNTESTED AND POTENTIALLY BROKEN
	# INVERTER
	def inverterGetList(self): return self.__callOpenDTUApi(method="GET", endpoint="inverter/list", useAuth=True)
	
	# def inverterAdd(self, data): return self.__callOpenDTUApi("POST", "inverter/add", data, True)
	
	# def inverterEdit(self, data): return self.__callOpenDTUApi("POST", "inverter/edit", data, True)
	
	# def inverterDelete(self, data): return self.__callOpenDTUApi("POST", "inverter/del", data, True)
	
	# def inverterOrder(self, data): return self.__callOpenDTUApi("POST", "inverter/order", data, True)
	
	def inverterGetRuntimeInfo(self, serial = None): return self.__callOpenDTUApi("GET", "livedata/status" + (f"?inv={serial}" if serial else ""))
	
	# def inverterStatsReset(self, serial): return self.__callOpenDTUApi("GET", f"inverter/stats_reset?inv={serial}", useAuth=True)
	
	def inverterGetDevinfo(self): return self.__callOpenDTUApi("GET", "devinfo/status")
	
	def inverterGetEventlog(self, serial): return self.__callOpenDTUApi("GET", f"eventlog/status?inv={serial}")
	
	def inverterGetGridProfile(self, serial): return self.__callOpenDTUApi("GET", f"gridprofile/status?inv={serial}")
	
	def inverterGetGridProfileRawData(self, serial): return self.__callOpenDTUApi("GET", f"gridprofile/rawdata?inv={serial}")
	
	def inverterGetLimitConfig(self): return self.__callOpenDTUApi("GET", "limit/status")
	
	def inverterSetLimitConfig(self, serial, data): return self.__callOpenDTUApi("POST", "limit/config", data | {"serial":serial}, useAuth=True)
	
	def inverterGetPowerConfig(self): return self.__callOpenDTUApi("GET", "power/status")
	
	def inverterSetPowerConfig(self, serial, data): return self.__callOpenDTUApi("POST", "power/config", data | {"serial":serial}, useAuth=True)
	
	# SYSTEM STATUS
	def systemGetStatus(self): return self.__callOpenDTUApi("GET", "system/status")
	
	# PROMETHEUS
	def prometheusGetMetrics(self): return self.__callOpenDTUApi("GET", "prometheus/metrics")
	
	# DTU
	def dtuGetConfig(self): return self.__callOpenDTUApi("GET", "dtu/config",useAuth=True)
	
	def dtuSetConfig(self, config): return self.__callOpenDTUApi("POST", "dtu/config", config, useAuth=True)
	
	# def dtuReboot(self, data): return self.__callOpenDTUApi("POST", "maintenance/reboot", data=data, useAuth=True)
	
	# MQTT
	def mqttGetStatus(self): return self.__callOpenDTUApi("GET", "mqtt/status")
	
	def mqttGetConfig(self): return self.__callOpenDTUApi("GET", "mqtt/config", useAuth=True)
	
	# def mqttSetConfig(self, config): return self.__callOpenDTUApi("POST", "mqtt/config", data=config, useAuth=True)
	
	# NTP
	def ntpGetStatus(self): return self.__callOpenDTUApi("GET", "ntp/status")

	def ntpGetConfig(self): return self.__callOpenDTUApi("GET", "ntp/config", useAuth=True)

	# def ntpSetConfig(self, data): return self.__callOpenDTUApi("POST", "ntp/config", data=data, useAuth=True)

	def ntpGetTime(self): return self.__callOpenDTUApi("GET", "ntp/time", useAuth=True)

	# def ntpSetTime(self, data): return self.__callOpenDTUApi("POST", "ntp/time", data=data, useAuth=True)

	# NETWORK
	def networkGetStatus(self): return self.__callOpenDTUApi("GET", "network/status")

	def networkGetConfig(self): return self.__callOpenDTUApi("GET", "network/config", useAuth=True)

	# HARDWARE
	# def networkSetConfig(self, data): return self.__callOpenDTUApi("POST", "network/config", data=data, useAuth=True)

	def deviceGetConfig(self): return self.__callOpenDTUApi("GET", "device/config", useAuth=True)

	def deviceSetConfig(self, data): return self.__callOpenDTUApi("POST", "device/config", data=data, useAuth=True)

	# SECURITY
	def securityGetConfig(self): return self.__callOpenDTUApi("GET", "security/config", useAuth=True)

	# def securitySetConfig(self, data): return self.__callOpenDTUApi("POST", "security/config", data=data, useAuth=True)

	def securityAuthenticate(self): return self.__callOpenDTUApi("GET", "security/authenticate", useAuth=True)

	# FILE
	def fileGet(self, fileName = "config.json"): return self.__callOpenDTUApi("GET", f"file/get?file={fileName}", useAuth=True)

	# def fileDelete(self, data): return self.__callOpenDTUApi("POST", "file/delete", data=data, useAuth=True)

	# def fileDeleteAll(self, data): return self.__callOpenDTUApi("POST", "file/delete_all", data=data, useAuth=True)

	def fileGetList(self): return self.__callOpenDTUApi("GET", "file/list", useAuth=True)

	# def fileUpload(self, data): return self.__callOpenDTUApi("POST", "file/upload", data=data, useAuth=True)

	# FIRMWARE
	# def firmwareUpdate(self, data): return self.__callOpenDTUApi("POST", "firmware/update", data=data, useAuth=True)

	# LOCALIZATION
	def i18nGetLanguages(self): return self.__callOpenDTUApi("GET", "i18n/languages")

	def i18nGetLanguage(self, languageCode): return self.__callOpenDTUApi("GET", f"i18n/language?code={languageCode}")

	# ================ CUSTOM FUNCTIONS ================ #
	def inverterGetSerial(self, index=0):
		return self.inverterGetList()["inverter"][index]["serial"]

	def __callOpenDTUApi(self, method, endpoint, data= None, useAuth= False, extraHeaders= None):
		if method == "GET":
			if useAuth:
				r = requests.get(
					url = f'{self.baseURL}{endpoint}',
					auth = HTTPBasicAuth(self.username, self.password),
					headers = extraHeaders
				)
			else:
				r = requests.get(url = f'{self.baseURL}{endpoint}', headers = extraHeaders)
		elif method == "POST":
			if (endpoint == "device/config"):
				files = {"data": (None, json.dumps(data).encode('utf-8')) }
				r = requests.post(
					url=f'{self.baseURL}{endpoint}', 
					auth=HTTPBasicAuth(self.username, self.password), 
					files=files
				)
			else:
				headers = {'Content-Type': 'application/x-www-form-urlencoded'}
				if extraHeaders:
					headers |= extraHeaders
				r = requests.post(
					url = f'{self.baseURL}{endpoint}',
					headers = headers,
					auth = HTTPBasicAuth(self.username, self.password), 
					data = f'data={data}' # Format must be manually set.
				)
		else:
			return None
		if r.status_code == 401: # Unauthorized. Response Text is empty, so return headers.
			return r.headers
		if r.headers["Content-Type"] == "application/json":
			return r.json()
		return r.text