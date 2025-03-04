import openDTU

username = "admin"
password = open(r"C:\Users\Simon\Desktop\programs\Files\openDTUAuth.pw").read().strip()
url = "http://192.168.178.48"
port = 80

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

dtu = openDTU(url, port, username, password)
# dconfig = dtu.deviceGetConfig()
# print(dconfig)
# print(dtu.deviceSetConfig({"curPin":{"name":"CMT, LEDs, Display"}}))
# print(dtu.i18nGetLanguages())
# print(dtu.i18nGetLanguage("en"))
print(dtu.inverterSetLimitConfig(dtu.inverterGetSerial(), {"limit_type":1, "limit_value":50}))
dtu.inverterGetGridProfile()