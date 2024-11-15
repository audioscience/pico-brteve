
import sys
import struct
import time

try:
    import micropython
    micropython = True
except ImportError:
    micropython = False

if micropython:
    from asi import spidev
else:
    import spidev2 as spidev

from asi import gpiod_utils as gpio

def spilock(func):
    """ Delegate function, to lock and unlocki SPI"""
    def wrapper(*args):
        ret = func(*args)
        return ret
    return wrapper


class BrtEveRP2040():
    """ Host platform RP2040 to control EVE, this class initialize,
    and set up SPI connection on RP2040, also set up the SDcard

    A host platform class must have below APIs:
     - transfer()
     - write_ili9488()
     - write_ili9488_cmd()
     - write_ili9488_data()
     - spi_sdcard -- SPI object of SDcard interface
    """

    def __init__(self):
		#configure SPI for Eve
        self._setup_spi()

    def _setup_sd(self, sdcs):
        """ Setup sdcard"""
        return True

    @spilock
    def _setup_spi(self):
        """ Setup SPI interface"""
        res = gpio.chip_open('/dev/gpiochip0')
        print(res)
        line_handle = gpio.chip_get_line(res, 24)
        print(res)
        res = gpio.line_request_output(line_handle, 'test', 0)
        print(res)
        print(gpio.line_get_value(line_handle))
        time.sleep(0.2)
        res = gpio.line_set_value(line_handle, 1)
        print(res)
        print(gpio.line_get_value(line_handle))
        time.sleep(0.1)
        spi = spidev.SPIBus('/dev/spidev0.0', 'w+b', speed_hz=10_000_000)
        self.spi = spi

    @spilock
    def transfer(self, write_data, bytes_to_read = 0):
        """ Transfer data via SPI"""
        # return bytes(self.spi.xfer3(list(write_data) + [0x00]*bytes_to_read))[-bytes_to_read:]
        return self.spi.transfer(tx_buf=write_data + b'\x00'*bytes_to_read, rx_buf=bytearray(len(write_data)+bytes_to_read))[-bytes_to_read:]

    def write_ili9488(self,cmd,data):
        """ Write command and data to ili9488 LCD"""
        # self.write_ili9488_cmd(cmd)
        # self.write_ili9488_data(data)
        pass

    @spilock
    def write_ili9488_cmd(self, cmd):
        """ Write command to ili9488 LCD"""
        # self.pin_cs_eve_ili9488.value = False
        # self.pin_dcx_eve_ili9488.value = False

        # self.spi_eve.write(cmd)
        # self.pin_cs_eve_ili9488.value = True
        pass

    @spilock
    def write_ili9488_data(self, data):
        """ Write data to ili9488 LCD"""
        # self.pin_cs_eve_ili9488.value = False
        # self.pin_dcx_eve_ili9488.value = True

        # self.spi_eve.write(data)
        # self.pin_cs_eve_ili9488.value = True
        pass
