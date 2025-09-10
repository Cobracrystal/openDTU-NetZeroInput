from openDTU import * 
username = "admin"
password = open(r"C:\Users\Simon\Desktop\programs\Files\openDTUAuth.pw").read().strip()
urlOpenDTU = "http://192.168.178.48"
port = 80

dtu = openDTU(urlOpenDTU, port, username, password)
main_inverter = dtu.inverterGetSerial(0)

setLimitResponse = dtu.inverterSetLimitConfig(main_inverter, {"limit_type":1, "limit_value":50})
dconfig = dtu.deviceGetConfig()
print("Old Config:")
print(dconfig)
manualConfig = {
	"curPin": {
		"name": "CMT, LEDs, Display",
		"nrf24": { "clk": -1,"cs": -1,"en": -1,"irq": -1,"miso": -1,"mosi": -1},
		"cmt": { "clk": 18, "cs": 4, "fcs": 5, "sdio": 23, "gpio2": 19, "gpio3": 16},
		"eth": { "enabled": False, "phy_addr": 0, "power": -1, "mdc": 23, "mdio": 18, "type": 0, "clk_mode": 0},
		"display": { "type": 3, "data": 21, "clk": 22, "cs": 255, "reset": 255 }
	},
	"display": { "rotation": 0, "power_safe": True, "screensaver": True, "contrast": 10, "language": 1, "diagramduration": 18000 }
}
LEDBrightness = 10
config = {"curPin":{"name":"CMT, LEDs, Display","nrf24":{"clk":-1,"cs":-1,"en":-1,"irq":-1,"miso":-1,"mosi":-1},"cmt":{"clk":18,"cs":4,"fcs":5,"sdio":23,"gpio2":19,"gpio3":16},"w5500":{"sclk":-1,"mosi":-1,"miso":-1,"cs":-1,"int":-1,"rst":-1},"eth":{"enabled":False,"phy_addr":0,"power":-1,"mdc":23,"mdio":18,"type":0,"clk_mode":0},"display":{"type":3,"data":21,"clk":22,"cs":255,"reset":255},"led":{"led0":25,"led1":26}},"display":{"rotation":0,"power_safe":True,"screensaver":True,"contrast":6,"locale":"de","diagramduration":18000,"diagrammode":1},"led":[{"brightness":LEDBrightness},{"brightness":LEDBrightness}]}
print(dtu.deviceSetConfig(config))
print(f'LED Brightness: {LEDBrightness}. New Config: ')
print(config)