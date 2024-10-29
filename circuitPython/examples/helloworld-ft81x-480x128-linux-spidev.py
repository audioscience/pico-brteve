
import time
from brteve.brt_eve_ft81x import BrtEve
from brteve.brt_eve_linux_spidev import BrtEveRP2040

host = BrtEveRP2040()
eve = BrtEve(host)
# eve.init(resolution="480x128", clk_external=False, touch="goodix")
eve.init(resolution="480x128", clk_external=False, touch="focaltech")

# eve.calibrate()
# eve.swap()

eve.ClearColorRGB(0xFF, 0x40, 0x20)
eve.ColorRGB(0xFF, 0xFF, 0xFF)
eve.Clear()
eve.cmd_text(eve.lcd_width // 2, eve.lcd_height // 3, 31, eve.OPT_CENTER, "AudioScience")
eve.cmd_text(eve.lcd_width // 30*18, eve.lcd_height // 24*14, 24, eve.OPT_CENTER, "Sound Egineering")
eve.cmd_text(eve.lcd_width // 30*21, eve.lcd_height // 24*20, 24, eve.OPT_CENTER, "Sonic Excellence")
eve.swap()
while (True):
	res = eve.get_inputs()
	if res.touch.x > 0 and res.touch.x < 480 and res.touch.y > 0 and res.touch.y < 128:
		eve.ClearColorRGB(0xFF, 0x40, 0x20)
		eve.Clear()
		eve.ColorRGB(0xFF, 0xFF, 0xFF)
		eve.cmd_text(eve.lcd_width // 2, eve.lcd_height // 3, 31, eve.OPT_CENTER, "AudioScience")
		eve.cmd_text(eve.lcd_width // 30*18, eve.lcd_height // 24*14, 24, eve.OPT_CENTER, "Sound Egineering")
		eve.cmd_text(eve.lcd_width // 30*21, eve.lcd_height // 24*20, 24, eve.OPT_CENTER, "Sonic Excellence")
		eve.ColorA(125)
		eve.ColorRGB(0x20, 0xF0, 0x00)
		eve.Begin(eve.POINTS)
		eve.Point_Size(26)
		eve.Vertex2f(res.touch.x, res.touch.y)
		eve.swap()
		# print(res.touch.x, res.touch.y)
	time.sleep(.05)
