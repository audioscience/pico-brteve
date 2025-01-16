
import time,sys
from brteve.brt_eve_ft81x import BrtEve
from brteve.brt_eve_linux_spidev import BrtEveRP2040

def eve_meter(x,y,w,h,level):
	eve.ColorRGB(0xFF, 0xFF, 0xFF)
	eve.cmd_text(x, y, 20, 0, str(level))

	eve.ColorRGB(0x00, 0xFF, 0x00)
	h = int(100-((-level*h)/100))
	# print(h)
	eve.Begin(eve.RECTS)
	eve.Vertex2ii(x, y-h, 0, 0)
	eve.Vertex2ii(x+w, y, 0, 0)
	eve.End()
	return


print("Eve init")
host = BrtEveRP2040()
eve = BrtEve(host)
#eve.init(resolution="480x128", clk_external=False, touch="")
eve.init(resolution="480x128", clk_external=False, touch="focaltech")
#eve.init(resolution="480x128", clk_external=False, touch="")
print("init done")

# eve.calibrate()
# eve.swap()

# set background to black
eve.ClearColorRGB(0x00, 0x00, 0x00)


level = 0
while(True):
	eve.Clear()
	eve.ColorRGB(0xFF, 0xFF, 0xFF)
	eve.cmd_text(0, 0, 20, 0, "IP: 192.168.1.1")
	w = 10
	h = 100
	for i in range(32):
		eve_meter(i*(w+5),110,w,h,level)
	level = level -5
	if(level<-100):
		level = 0
	time.sleep(0.050)
	eve.swap()
	#break

"""
eve.ColorRGB(0xFF, 0xFF, 0xFF)
#eve.Begin(eve.RECTS)
#eve.Vertex2ii(4+0, 18+0, 0,0)
#eve.Vertex2ii(4+116, 18+48,0,0)
#eve.End()
eve.cmd_text(0, 0, 20, 0, "IP: 192.168.1.1")
eve.cmd_text(0, 10, 21, 0, "IP: 192.168.1.1")
# eve.swap()

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
"""
