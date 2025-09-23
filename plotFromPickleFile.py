import sys
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
update_interval = 2000 # Time in milliseconds between each update
checkInterval = 250 # Time in milliseconds between each check
max_graph_width = 10000 # Number of datapoints the graph should keep. CURRENTLY NOT USED.
battery_voltage_threshold = 48.5 # Threshold below which connection with battery is stopped.
displayGraph = True # Whether to display a graph at all. Also a command line argument. This value is used if no cmd arg is given.
onlyPlot = True # Whether to only plot without changing the limit. Also a command line argument. This value is used if no cmd arg is given.


if len(sys.argv) > 1:
	try:
		graphTime, graphPowerLimit, graphBatteryPower, graphPowerConsumption = pickle.load(open(sys.argv[1], "rb"))
		print(f'Lade Daten von {sys.argv[1]}..')
	except:
		print(f'Gegebene Datei {sys.argv[1]} konnte nicht geladen werden.')
		sys.exit(1)
	figure, axes = plt.subplots(num='Leistung')
	line0, = plt.plot(graphTime, graphPowerLimit, 'b', label='Wechselrichterlimit')
	line1, = plt.plot(graphTime, graphBatteryPower, 'g', label='Wechselrichterleistung')
	line2, = plt.plot(graphTime, graphPowerConsumption, 'r', label='Stromverbrauch')
	figure.autofmt_xdate()
	figure.tight_layout()
	plt.ylabel("Leistung")
	plt.legend()
	axes.xaxis.set_major_formatter(dates.DateFormatter("%H:%M:%S"))
	axes.relim()
	line0.set_data(graphTime, graphPowerLimit)
	line1.set_data(graphTime, graphBatteryPower)
	line2.set_data(graphTime, graphPowerConsumption)
	plt.show()
	sys.exit(1)
		