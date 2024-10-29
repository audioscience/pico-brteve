from brteve.brt_eve_ft81x import BrtEve
from brteve.brt_eve_linux_spidev import BrtEveRP2040

host = BrtEveRP2040()
eve = BrtEve(host)
eve.init(resolution="480x128", clk_external=False)

eve.ClearColorRGB(0xFF, 0x40, 0x20)
eve.Clear()
eve.cmd_text(eve.lcd_width // 2, eve.lcd_height // 3, 31, eve.OPT_CENTER, "AudioScience")
eve.cmd_text(eve.lcd_width // 30*18, eve.lcd_height // 24*14, 24, eve.OPT_CENTER, "Sound Egineering")
eve.cmd_text(eve.lcd_width // 30*21, eve.lcd_height // 24*20, 24, eve.OPT_CENTER, "Sonic Excellence")
eve.swap()
