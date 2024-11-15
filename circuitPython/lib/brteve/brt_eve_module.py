""" BridgeTek EVE module """
import time
import struct
from collections import namedtuple

if not hasattr(time, 'monotonic'):
    time.monotonic = lambda: time.ticks_ms() / 1000.0

from .brt_eve_movie_player import BrtEveMoviePlayer
from .brt_eve_common import BrtEveCommon, align4

# Order matches the register layout, so can fill with a single block read
_Touch = namedtuple(
    "TouchInputs",
    (
    "rawy",
    "rawx",
    "rz",
    "y",
    "x",
    "tag_y",
    "tag_x",
    "tag",
    ))
_State = namedtuple(
    "State",
    (
    "touching",
    "press",
    "release"
    ))
_Tracker = namedtuple(
    "Tracker",
    (
    "tag",
    "val"
    ))
_Inputs = namedtuple(
    "Inputs",
    (
    "touch",
    "tracker",
    "state",
    ))

class CoprocessorException(Exception):
    """Raise exception on faulty"""

def is_eve_faulty(read_pointer):
    """Check if EVE read pointer is faulty or not"""
    return read_pointer & 0x3

def get_transfer_addess(address):
    """Pack an address"""
    return struct.pack(">I", address)[1:]

class BrtEveModule(BrtEveCommon, BrtEveMoviePlayer): # pylint: disable=too-many-instance-attributes,too-many-public-methods
    """EVE management, including boot up and transfer data, via SPI port"""

    FIFO_MAX = (0xffc) # Maximum reported free space in the EVE command FIFO
    command_write_pointer = 0 # internal command_write_pointer position
    EVE_CMD_FIFO_SIZE =((4) * 1024) # 4kB coprocessor FIFO size
    EVE_CMD_FIFO_MASK =(EVE_CMD_FIFO_SIZE - 1)

    def __init__(self):
        self.host = None # This is set in brt_eve_[chip id].py
        self.eve = None # This is set in brt_eve_[chip id].py

        self.lcd_width=1280
        self.lcd_height=800

        self.space = 0
        self.prev_touching = 0
        self.inputs = 0

    def init(self, resolution = "", touch = "", clk_external=True):
        """Start up EVE and light up LCD"""

        print("Initialing for MCU " + self.eve.eve_type)
        self.eve.register(self)
        self.coldstart(clk_external=clk_external)

        # Programming Guide 2.4: Initialization Sequence during Boot Up
        time_start = time.monotonic()
        while self.rd32(self.eve.REG_ID) != 0x7c:
            assert (time.monotonic() - time_start) < 1.0, "No response - is device attached?"

        time_start = time.monotonic()
        while self.rd16(self.eve.REG_CPURESET) != 0x0:
            assert(time.monotonic() - time_start) < 1.0, "EVE engines failed to reset"

        self.getspace()

        print("ID %x  %x %x %x" % (
            self.rd32(self.eve.REG_ID),
            self.rd32(0xc0000),
            self.rd32(self.eve.REG_HSIZE),
            self.rd32(self.eve.REG_VSIZE)))

        self.standard_startup()

        if resolution == "800x480":
            self.setup_800x480()
        if resolution == "800x480_NoSquare":
            self.setup_800x480_NoSquare()
        if resolution == "1280x720":
            self.setup_1280x720()
        if resolution == "1280x800":
            self.setup_1280x800()
        if resolution == "1024x600":
            self.setup_1024x600()
        if resolution == "480x272":
            self.setup_480x272()
        if resolution == "480x128":
            self.setup_480x128()
        if resolution == "640x480":
            self.setup_640x480()
        if resolution == "320x480":
            self.init_ili9488()
            self.setup_320x480()

        if touch != "":
            self.setup_touch(touch)

        self.lcd_width = self.rd32(self.eve.REG_HSIZE)
        self.lcd_height = self.rd32(self.eve.REG_VSIZE)

    def spi_sdcard(self):
        """ Return SPI sdcard object"""
        return self.host.spi_sdcard

    def eve_system_clk(self, freq):
        """Setting EVE's system clock"""
        if self.eve.eve_type == "ft80x":
            if self.eve.EVE_SYSCLK_24M == freq:
                self.host_cmd(self.eve.EVE_PLL_24M)
            elif self.eve.EVE_SYSCLK_36M == freq:
                self.host_cmd(self.eve.EVE_PLL_36M)
            elif self.eve.EVE_SYSCLK_48M == freq:
                self.host_cmd(self.eve.EVE_PLL_48M)
            else:
                print("Invalid sys clk frequency selected (%i)\n", freq)
        else:
            if self.eve.EVE_SYSCLK_24M == freq:
                self.host_cmd(0x61, 0x02)
            elif self.eve.EVE_SYSCLK_36M == freq:
                self.host_cmd(0x61, 0x03)
            elif self.eve.EVE_SYSCLK_48M == freq:
                self.host_cmd(0x61, 0x44)
            elif self.eve.EVE_SYSCLK_60M == freq:
                self.host_cmd(0x61, 0x45)
            elif self.eve.EVE_SYSCLK_72M == freq:
                self.host_cmd(0x61, 0x46)
            elif self.eve.EVE_SYSCLK_DEFAULT == freq:
                self.host_cmd(0x61)

    def coldstart(self, clk_external=True):
        """Start up EVE"""
        freq = self.eve.EVE_SYSCLK_60M #60Mhz is default for FT8xx
        if ( self.eve.eve_type == 'bt815_6' or
             self.eve.eve_type == 'bt817_8' ):
            freq = self.eve.EVE_SYSCLK_72M #72Mhz is default for BT8xx

        self.eve_system_clk(freq)
        if clk_external:
            self.host_cmd(0x44)         # Select PLL input from external clock source
        self.host_cmd(0x00)         # Wake up
        self.host_cmd(0x68)         # Core reset

    def host_cmd(self, byte_a, byte_b = 0, byte_c = 0):
        """Send a host command"""
        self.host.transfer(bytes([byte_a, byte_b, byte_c]))

    def standard_startup(self):
        """Clean up command fifo at start up"""
        self.Clear(1,1,1)
        self.swap()
        self.finish()

        self.wr32(self.eve.REG_GPIO_DIR, 0xff)
        self.wr32(self.eve.REG_GPIO, 0xff)

        time.sleep(.1)

    def cmd_regwrite(self, reg, value):
        """Write value to a register"""
        self.wr32(reg, value)

    def pad_drive_strength(self, strength, group):
        """ Set the drive strength for various pins
        :param strength: Drive strength
        :param group: Pin group to set
        :return: none
        """
        self.eve.host_cmd(0x70, group, strength)

    def transfer_read(self, address, number):
        """Transfer data to SPI in read mode"""
        dummy_bytes = 1
        return self.host.transfer(
            get_transfer_addess(address), dummy_bytes + number)[dummy_bytes:]

    def transfer_write(self, address, value):
        """Transfer data to SPI in write mode"""
        self.host.transfer(get_transfer_addess(0x800000 | address) + value)

    def rd8(self, address):
        """Get write pointer address"""
        return struct.unpack("<B", self.transfer_read(address, 1))[0]

    def rd16(self, address):
        """Read a number 16 bits"""
        return struct.unpack("<H", self.transfer_read(address, 2))[0]

    def rd32(self, address):
        """Read a number 32 bits"""
        return struct.unpack("<I", self.transfer_read(address, 4))[0]

    def wr8(self, address, value):
        """Write a number 8 bits """
        self.command_write_pointer += 1
        self.command_write_pointer &= self.EVE_CMD_FIFO_MASK
        self.transfer_write(address, struct.pack("B", value))

    def wr16(self, address, value):
        """Write a number 16 bits """
        self.command_write_pointer += 2
        self.command_write_pointer &= self.EVE_CMD_FIFO_MASK
        self.transfer_write(address, struct.pack("H", value))

    def wr32(self, address, value):
        """Write a number 32 bits """
        self.command_write_pointer += 4
        self.command_write_pointer &= self.EVE_CMD_FIFO_MASK
        self.transfer_write(address, struct.pack("I", value))

    def write_mem(self, address, buff):
        """Write a buffer to EVE"""
        self.transfer_write(address, buff)

    def read_mem(self, address, size):
        """Write a buffer to EVE"""
        return self.transfer_read(address, size)

    def write_file(self, address, file):
        """Write a buffer to EVE's RAM_G"""
        chunksize = 1000
        with open(file, 'rb') as file_handle:
            while True:
                buff = file_handle.read(chunksize)
                if not buff:
                    break # done
                self.transfer_write(address, buff)
                address += len(buff)
        return address

    def eve_write_pointer(self):
        """Get write pointer value"""
        return self.rd32(self.eve.REG_CMD_WRITE) & self.EVE_CMD_FIFO_MASK

    def eve_read_pointer(self):
        """Get read pointer value"""
        return self.rd16(self.eve.REG_CMD_READ) & self.EVE_CMD_FIFO_MASK

    def getspace(self):
        """Query space of command fifo"""
        if ( self.eve.eve_type == "bt815_6" or
             self.eve.eve_type == "bt817_8" ):
            self.space = self.rd16(self.eve.REG_CMDB_SPACE) & self.EVE_CMD_FIFO_MASK
            if is_eve_faulty(self.space):
                print("Co-processor faulty")
                raise CoprocessorException
        else:
            write_pointer = self.eve_write_pointer()
            read_pointer = self.eve_read_pointer()
            self.space = (read_pointer - write_pointer - 4) & self.EVE_CMD_FIFO_MASK

        if self.space & 1:
            print("Co-processor faulty")
            raise CoprocessorException

    def reserve(self, num):
        """Wait until command fifo have enough space"""
        while self.space < num:
            self.getspace()
        self.command_write_pointer = self.eve_write_pointer() & self.EVE_CMD_FIFO_MASK

    def is_finished(self):
        """Query if EVE is idle"""
        self.getspace()
        return self.space == self.FIFO_MAX

    def write(self, buffer):
        """Write a buffer to EVE's command fifo"""
        self.reserve(len(buffer))
        if ( self.eve.eve_type == "bt815_6" or
             self.eve.eve_type == "bt817_8" ):
            self.transfer_write(self.eve.REG_CMDB_WRITE, buffer)
        else:
            self.transfer_write(self.eve.RAM_CMD + self.command_write_pointer, buffer)
            self.command_write_pointer += len(buffer)
            self.command_write_pointer &= self.EVE_CMD_FIFO_MASK
            self.wr32(self.eve.REG_CMD_WRITE, self.command_write_pointer)

        self.getspace()

    def finish(self):
        """Flush command queue and wait until EVE is idle"""
        self.flush()
        self.reserve(self.FIFO_MAX)

    def VertexFormat(self, fmt):  # pylint: disable=invalid-name
        """Overwride function VertexFormat of _EVE class, do nothing if ft80x is in use"""
        if self.eve.eve_type == "ft80x":
            pass
        else:
            super().VertexFormat(fmt)

    def result(self, num=1):
        """Return the result field of the preceding command"""
        self.finish()
        write_pointer = self.rd32(self.eve.REG_CMD_READ)
        return self.rd32(self.eve.RAM_CMD + (4095 & (write_pointer - 4 * num)))

    def setup_touch(self, touch = ""):
        """Setting touch"""
        if touch == "focaltech":
            self.wr8(self.eve.REG_TOUCH_MODE, self.eve.TMODE_FRAME)
            self.wr8(self.eve.REG_CTOUCH_EXTENDED, 1)
            self.wr8(self.eve.REG_CPURESET, 2)
            self.wr16(self.eve.REG_TOUCH_CONFIG, 0x0381) # Address 0x38 , FocalTech FT5426 ?
            time.sleep(0.1)
            self.wr8(self.eve.REG_CPURESET, 0)
            time.sleep(0.1)
        if touch == "goodix":
            goodix_setup_bin = [
                0x1A,0xFF,0xFF,0xFF,0x20,0x20,0x30,0x00,0x04,0x00,0x00,0x00,0x02,0x00,0x00,0x00,
                0x22,0xFF,0xFF,0xFF,0x00,0xB0,0x30,0x00,0x78,0xDA,0xED,0x54,0xDD,0x6F,0x54,0x45,
                0x14,0x3F,0x33,0xB3,0x5D,0xA0,0x94,0x65,0x6F,0x4C,0x05,0x2C,0x8D,0x7B,0x6F,0xA1,
                0x0B,0xDB,0x9A,0x10,0x09,0x10,0x11,0xE5,0x9C,0x4B,0x1A,0x0B,0x0D,0x15,0xE3,0x03,
                0x10,0xFC,0xB8,0xB3,0x2D,0xDB,0x8F,0x2D,0x29,0x7D,0x90,0x48,0x43,0x64,0x96,0x47,
                0xBD,0x71,0x12,0x24,0x11,0xA5,0x64,0xA5,0xC6,0x10,0x20,0x11,0x95,0xC4,0xF0,0x80,
                0xA1,0x10,0xA4,0x26,0x36,0xF0,0x00,0xD1,0x48,0x82,0x0F,0x26,0x7D,0x30,0x42,0x52,
                0x1E,0x4C,0x13,0x1F,0xAC,0x67,0x2E,0x8B,0x18,0xFF,0x04,0xE3,0x9D,0xCC,0x9C,0x33,
                0x73,0x66,0xCE,0xE7,0xEF,0xDC,0x05,0xAA,0x5E,0x81,0x89,0x4B,0xC2,0xD8,0x62,0x5E,
                0x67,0x75,0x73,0x79,0x4C,0x83,0xB1,0x7D,0x59,0x7D,0x52,0x7B,0x3C,0xF3,0x3A,0x8E,
                0xF2,0xCC,0xB9,0xF3,0xBC,0x76,0x9C,0xE3,0x9B,0xCB,0xEE,0xEE,0xC3,0xFB,0xCD,0xE5,
                0x47,0x5C,0x1C,0xA9,0xBE,0xB8,0x54,0x8F,0x71,0x89,0x35,0xF4,0x67,0xB5,0xED,0x57,
                0xFD,0x71,0x89,0xE9,0x30,0x0C,0xC6,0xA5,0xB5,0x68,0x8B,0x19,0x54,0xFD,0x9B,0x72,
                0x4A,0xBF,0x00,0x36,0x8A,0xA3,0x0C,0x3E,0x83,0xCF,0x81,0x17,0xD9,0x22,0x5B,0x1F,
                0x80,0x41,0xF6,0xA3,0xAF,0xD5,0x08,0x93,0xD5,0x6B,0x23,0xCB,0x5E,0x6C,0x03,0x6F,
                0x28,0xAB,0x53,0x18,0x0F,0xA5,0xB1,0xDE,0x74,0x61,0x17,0xBC,0x8C,0xCE,0x96,0x2A,
                0x66,0xB5,0x57,0x4E,0x56,0xB6,0xAA,0x86,0xD7,0xF1,0x79,0x1A,0xF3,0xFC,0x02,0x4C,
                0x73,0xD9,0x8B,0xDE,0xCE,0xAD,0x88,0x84,0x51,0x3D,0x23,0xB9,0x27,0x71,0x17,0x2E,
                0xC7,0x4C,0xB2,0x36,0x97,0xB7,0xE0,0x00,0x28,0xBD,0x1C,0x95,0xB6,0x3A,0x83,0x4F,
                0x98,0x1E,0x4C,0x22,0x62,0xEA,0xA2,0xD8,0x85,0x8D,0x66,0x27,0xAA,0x28,0xC0,0x65,
                0x35,0xC9,0x92,0xBF,0x25,0x4D,0x2C,0xB1,0xD1,0x4A,0xD3,0x05,0xCE,0xBB,0x05,0x06,
                0xD8,0x2F,0x35,0x60,0x7B,0x16,0x32,0x67,0xFB,0xC0,0x54,0x11,0x4A,0xE3,0xB9,0x38,
                0x6A,0x33,0x5B,0xA1,0x60,0xB6,0xA3,0x30,0xAB,0x8D,0x8B,0x41,0x98,0x42,0x42,0x0B,
                0x66,0x2B,0x9E,0x4B,0x24,0x50,0x93,0xB8,0x93,0x8B,0x70,0x11,0xEB,0xD8,0x67,0x6F,
                0xEF,0xF5,0x5C,0x0A,0xAF,0xC2,0x28,0x2C,0x3A,0x7D,0x05,0x3B,0x70,0x32,0x67,0xF5,
                0x04,0x4E,0xC0,0x05,0x9C,0xC2,0x33,0x3C,0xBF,0x86,0x4B,0x6E,0xAD,0xED,0x2E,0xC0,
                0x79,0x9C,0xC0,0x73,0xB8,0xDA,0x78,0x43,0x3F,0x73,0x2E,0x0B,0x66,0x0A,0x61,0xE8,
                0x32,0xEB,0x72,0xB6,0x94,0x76,0xB2,0x29,0xBC,0x0C,0x87,0x4D,0xCA,0x7C,0x0C,0x60,
                0xEE,0x23,0xA1,0xEA,0xBD,0x81,0x17,0xF9,0xD4,0x8B,0xE6,0x19,0x35,0x30,0xCD,0x34,
                0x5D,0xA3,0x75,0x35,0x9A,0xAA,0x51,0x55,0xA3,0xB2,0x46,0x45,0x42,0xA7,0xF1,0x0E,
                0x2E,0xF1,0x01,0xE2,0x88,0x98,0xB3,0xC5,0x3B,0xB8,0x94,0xFE,0x31,0x84,0x30,0x0F,
                0xB0,0x89,0xC0,0x4C,0x83,0xC4,0x69,0x68,0xA2,0x56,0x51,0xA0,0xA5,0xFF,0x1A,0xAD,
                0xA2,0x89,0x56,0x91,0xD2,0xB7,0xC0,0x37,0xAF,0xC2,0xD3,0x3C,0x5B,0x78,0xE6,0xB8,
                0xAE,0x1B,0x29,0x83,0x9B,0x28,0xE0,0x1D,0x57,0xB3,0xE8,0x10,0x37,0x37,0x07,0xA5,
                0x93,0x51,0x17,0xA5,0x31,0x65,0x36,0xE0,0x4B,0xB4,0x51,0x6C,0x12,0x1D,0xE2,0x45,
                0xE1,0x6E,0xAF,0xE0,0x2A,0xD4,0x19,0x2F,0x82,0xC1,0x6E,0xEA,0xC0,0xD7,0xFC,0x38,
                0x4A,0xA2,0x18,0x2E,0xFB,0xAE,0x36,0x6A,0x44,0xF5,0x0E,0x09,0x9B,0xA0,0x16,0x78,
                0xCF,0x68,0xF0,0x1D,0x5A,0xB2,0x8C,0x1C,0x18,0xDC,0x2F,0xA6,0x70,0x3D,0xFB,0xD0,
                0xC0,0x6F,0x38,0xEF,0xEE,0x5D,0xFF,0xFB,0x3E,0x63,0x20,0xC1,0x4B,0x3D,0xBE,0xEB,
                0x7B,0xE5,0x6E,0xDA,0xC2,0x55,0x4F,0xE1,0x3B,0x62,0x14,0xEE,0xE3,0xEB,0xDC,0x0B,
                0xDD,0x95,0x19,0xB4,0x74,0xC2,0x9F,0x6F,0x60,0xC0,0x18,0xD5,0x3B,0x8B,0xB3,0x9C,
                0xD7,0x45,0xE6,0x13,0x18,0x23,0x87,0x75,0xCE,0xAB,0xCE,0xA2,0x43,0x81,0xEA,0x3D,
                0xEB,0x0B,0x68,0x67,0x54,0x40,0xDF,0xA7,0xFE,0x28,0xA3,0x65,0x5C,0x54,0x2B,0x96,
                0x2E,0xF9,0xDB,0xCD,0x07,0x74,0x0B,0x5B,0x68,0x3D,0x39,0x4B,0xDF,0x08,0x30,0x19,
                0x1C,0x77,0xFC,0xDE,0x71,0x31,0x56,0xF9,0x4A,0xB4,0xD3,0x9C,0xB5,0x3D,0xD7,0xA8,
                0x9D,0x07,0xFB,0xC7,0x96,0xF2,0xFA,0x5B,0x3A,0x84,0x5E,0x79,0x07,0x35,0x97,0x8B,
                0x62,0x06,0xA5,0x99,0x45,0xD6,0x20,0x6E,0xD3,0x64,0x65,0x1F,0x59,0x2D,0x51,0x62,
                0x17,0xCD,0xCD,0xC5,0xD1,0x6D,0xBA,0xC6,0x23,0x8D,0xBF,0xF9,0x19,0x3C,0x84,0xDF,
                0x99,0xFB,0x62,0x14,0xEF,0x92,0x8B,0x14,0xD9,0xFA,0x29,0xFA,0x89,0x3A,0xB1,0x5A,
                0x39,0x4F,0x33,0x6C,0xE9,0x14,0xFD,0xC2,0xBB,0x31,0xDE,0xCD,0x72,0x8D,0x60,0x30,
                0xAF,0xDB,0x6B,0x36,0x6F,0x8A,0x16,0x9A,0x67,0x6C,0x4F,0x3A,0xFC,0xB3,0xB2,0x4F,
                0xA4,0xC3,0x02,0x99,0x24,0x27,0xAA,0xC7,0xC9,0xA7,0xC5,0x55,0x6A,0x08,0x3B,0xB1,
                0x51,0x2E,0x38,0x02,0xE6,0x4B,0x72,0x11,0x37,0x70,0xBC,0x41,0xD0,0x89,0x4D,0x72,
                0x0A,0x73,0x37,0x3A,0xD0,0xC5,0xAD,0x7A,0x57,0x06,0x8C,0x6E,0x2A,0xD0,0x7C,0xA3,
                0x46,0x6C,0xF1,0x68,0x12,0xF5,0x62,0xD6,0xBB,0x86,0x35,0x2A,0xDD,0x16,0xB6,0x85,
                0xD3,0x74,0x94,0xB1,0xC2,0xD1,0xC0,0x55,0x5A,0xC7,0x3A,0x37,0xCB,0x02,0xE5,0x13,
                0x89,0xBB,0xA1,0xE4,0x9A,0x70,0xCB,0x91,0x7D,0xF4,0xBC,0xDC,0x76,0xE4,0x29,0xC9,
                0xB5,0x29,0xC3,0x90,0xD7,0xB7,0x33,0x50,0xFA,0x15,0xD9,0x10,0xD9,0xC8,0xEB,0x6D,
                0xE3,0xBC,0x7A,0xDA,0x8E,0x3C,0xAA,0xE0,0x70,0xF0,0xB8,0x82,0xE5,0xE0,0x71,0x05,
                0xDF,0x94,0xA3,0x50,0xA5,0xB7,0x82,0xBB,0x84,0x74,0x40,0xEE,0xA1,0x55,0xDC,0x73,
                0x8B,0xCD,0x62,0xE3,0xF4,0x1D,0x66,0x7D,0x07,0x25,0xF3,0x7B,0xDF,0x0B,0x1A,0x5C,
                0x3F,0xF3,0x74,0x3D,0xBF,0x8A,0x7B,0xF4,0xA0,0x54,0xBA,0x4A,0x1F,0x05,0xAE,0xF7,
                0x77,0x87,0xC7,0xF8,0xFD,0x87,0xF2,0x61,0x66,0x91,0xBE,0x90,0x0E,0x55,0xEE,0xDD,
                0xE7,0xC1,0x9E,0x30,0xCD,0x19,0x78,0xF8,0x0F,0xDC,0x1D,0x9E,0x09,0x46,0xB9,0x1E,
                0x67,0xE5,0x21,0xFE,0x17,0xED,0xA0,0xAC,0x3E,0xC1,0x5A,0xDE,0xE0,0xE8,0x0E,0xC8,
                0x38,0x5A,0x68,0x8E,0xE3,0x78,0x6E,0x06,0x15,0xD3,0xCB,0x41,0x96,0x63,0x97,0xDC,
                0xF7,0x57,0xA4,0x32,0x9F,0x31,0xEF,0xEA,0x3A,0x8E,0x00,0x6D,0x6C,0x7B,0x12,0x4F,
                0xE3,0x24,0x64,0xF8,0xDE,0xCD,0x60,0x7F,0x78,0x1A,0xAB,0xE4,0x45,0x3F,0x24,0x11,
                0xFC,0xC8,0x11,0x74,0xF2,0xBB,0xE3,0x58,0x8F,0xF7,0x02,0x4B,0xBF,0x06,0x82,0x3B,
                0xBC,0x0B,0x37,0xF0,0x1F,0xF3,0x7A,0x98,0xE2,0xB7,0xCF,0x9A,0x49,0xBC,0x27,0xDB,
                0x2B,0x69,0xDE,0x57,0x29,0x8F,0x8D,0x8C,0xAF,0x49,0x70,0xB8,0xFC,0x3D,0xB8,0x10,
                0x5A,0xFA,0x23,0xA8,0x52,0x77,0xB0,0x39,0x74,0x5E,0xC8,0x96,0x16,0xBE,0xB3,0x2C,
                0x68,0x0C,0xEB,0x54,0x95,0x66,0xFC,0x59,0x9A,0xC1,0x63,0xE4,0x6A,0xF2,0x7D,0xF8,
                0x40,0xC2,0xFF,0xDF,0x7F,0xF2,0x53,0x0B,0xFF,0x02,0x46,0xD6,0xE2,0x80,0x00,0x00,
                0x1A,0xFF,0xFF,0xFF,0x14,0x21,0x30,0x00,0x04,0x00,0x00,0x00,0x0F,0x00,0x00,0x00,
                0x1A,0xFF,0xFF,0xFF,0x20,0x20,0x30,0x00,0x04,0x00,0x00,0x00,0x00,0x00,0x00,0x00]
            print("Setup touch for Goodix\n")
            # self.wr8(self.eve.REG_ADAPTIVE_FRAMERATE, 0);
            # self.wr8(self.eve.REG_CPURESET, 2)
            # self.wr16(self.eve.REG_TOUCH_CONFIG, 0x05d0)
            # self.wr8(self.eve.REG_CPURESET, 0)
            # time.sleep(0.3)

            self.wr8(self.eve.REG_TOUCH_MODE, self.eve.TMODE_FRAME)
            self.wr8(self.eve.REG_CTOUCH_EXTENDED, 1)

            # print(len(goodix_setup_bin))
            # self.write(bytes(goodix_setup_bin))
            self.finish()

            self.wr8(self.eve.REG_CPURESET, 2)
            # self.wr16(self.eve.REG_TOUCH_CONFIG, 0x05d0)
            self.wr16(self.eve.REG_TOUCH_CONFIG, 0x0381) # Address 0x38 , FocalTech FT5426 ?

            # gpio_dir = self.rd16(self.eve.REG_GPIOX_DIR)
            # self.wr16(self.eve.REG_GPIOX_DIR, gpio_dir | 0xF)
            # gpio_val = self.rd16(self.eve.REG_GPIOX)
            # self.wr16(self.eve.REG_GPIOX, gpio_val & 0xFFF0)

            time.sleep(0.1)
            self.wr8(self.eve.REG_CPURESET, 0)
            time.sleep(0.1)
            # self.wr16(self.eve.REG_GPIOX, gpio_val | 0xF)
            # self.wr16(self.eve.REG_GPIOX_DIR, gpio_dir & 0xFFF0)



    def init_ili9488(self):
        """Init for ili9488 LCD"""
        #Toggle RESX pin of ILI9488 to complete power-on reset process
        self.wr32(self.eve.REG_GPIO, 0x0)
        time.sleep(0.002)
        self.wr32(self.eve.REG_GPIO, 0x83)

        ili9488_cmd_software_reset = b'\x01'
        ili9488_cmd_colomnaddr = b'\x2a'
        ili9488_cmd_rowaddr = b'\x2b'

        ili9488_cmd_interface_mode_control = b'\xb0'
        ili9488_cmd_frame_rate_control = b'\xb1'
        ili9488_cmd_interface_pixel_format = b'\x3a'
        ili9488_interface_pixel_format_18bit_dpi = b'\x66'
        ili9488_cmd_imagefunction = b'\xe9'
        ili9488_cmd_write_control_display = b'\x53'
        ili9488_cmd_madctrl = b'\x36'

        ili9488_cmd_display_function_control = b'\xb6'
        ili9488_cmd_sleep_out = b'\x11'
        ili9488_cmd_displayon = b'\x29'


        self.host.write_ili9488_cmd(ili9488_cmd_software_reset)
        time.sleep(0.00012)

        #colomn address set - 0 to 319
        self.host.write_ili9488(ili9488_cmd_colomnaddr,bytes([0x00,0x00,0x01, 0x3f]))
        #row address set - 0 to 479
        self.host.write_ili9488(ili9488_cmd_rowaddr,bytes([0x00,0x00,0x01, 0xdf]))

        #frame rate 70hz
        self.host.write_ili9488(ili9488_cmd_frame_rate_control,b'\xb0')

        #adjust control 3
        self.host.write_ili9488(b'\xf7', bytes([0xa9,0x51,0x2c,0x82]))

        self.host.write_ili9488(ili9488_cmd_interface_mode_control, b'\x02')
        self.host.write_ili9488(
            ili9488_cmd_interface_pixel_format,
            ili9488_interface_pixel_format_18bit_dpi)
        self.host.write_ili9488(ili9488_cmd_imagefunction, b'\x00')
        self.host.write_ili9488(ili9488_cmd_write_control_display, b'\x2c')

        #bgr connection and colomn address order
        self.host.write_ili9488(ili9488_cmd_madctrl,b'\x48')

        self.host.write_ili9488(ili9488_cmd_display_function_control, bytes([0x30,0x02,0x3b]))

        self.host.write_ili9488_cmd(ili9488_cmd_sleep_out)
        time.sleep(0.02)

        self.host.write_ili9488_cmd(ili9488_cmd_displayon)

    def setup_1280x720(self):
        """Default setting for LCD 1280x720"""
        self.Clear()
        self.swap()
        setup = [
            (self.eve.REG_OUTBITS, 0),
            (self.eve.REG_DITHER, 0),
            (self.eve.REG_CSPREAD, 0),
            (self.eve.REG_PCLK_POL, 0),
            (self.eve.REG_HCYCLE, 1650),
            (self.eve.REG_HOFFSET, 260),
            (self.eve.REG_HSIZE, 1280),
            (self.eve.REG_VCYCLE, 750),
            (self.eve.REG_VOFFSET, 225),
            (self.eve.REG_VSIZE, 720),
            (self.eve.REG_HSYNC1, 0),
            (self.eve.REG_HSYNC0, 40),
            (self.eve.REG_VSYNC1, 0),
            (self.eve.REG_VSYNC0, 5),
            (self.eve.REG_ADAPTIVE_FRAMERATE, 0),
            (self.eve.REG_PCLK, 1),
        ]
        for (adress, value) in setup:
            self.cmd_regwrite(adress, value)

    def setup_320x240(self):
        """Default setting for LCD QVGA 320x240"""
        self.Clear()
        self.swap()
        setup = [
            (self.eve.REG_DITHER, 1),
            (self.eve.REG_CSPREAD, 1),
            (self.eve.REG_PCLK_POL, 0),
            (self.eve.REG_SWIZZLE, 2),

            (self.eve.REG_HCYCLE, 408),
            (self.eve.REG_HOFFSET, 70),
            (self.eve.REG_HSIZE, 320),

            (self.eve.REG_HSYNC1, 10),
            (self.eve.REG_HSYNC0, 0),

            (self.eve.REG_VCYCLE, 263),
            (self.eve.REG_VOFFSET, 13),
            (self.eve.REG_VSIZE, 240),

            (self.eve.REG_VSYNC1, 2),
            (self.eve.REG_VSYNC0, 0),
            (self.eve.REG_PCLK, 8),
        ]
        for (adress, value) in setup:
            self.cmd_regwrite(adress, value)

    def setup_320x480(self):
        """Default setting for LCD HVGA 320x480"""
        self.Clear()
        self.swap()
        setup = [
            (self.eve.REG_DITHER, 1),
            (self.eve.REG_CSPREAD, 1),
            (self.eve.REG_PCLK_POL, 1),
            (self.eve.REG_SWIZZLE, 2),

            (self.eve.REG_HCYCLE, 400),
            (self.eve.REG_HOFFSET, 40),
            (self.eve.REG_HSIZE, 320),

            (self.eve.REG_HSYNC1, 10),
            (self.eve.REG_HSYNC0, 0),

            (self.eve.REG_VCYCLE, 500),
            (self.eve.REG_VOFFSET, 10),
            (self.eve.REG_VSIZE, 480),

            (self.eve.REG_VSYNC1, 5),
            (self.eve.REG_VSYNC0, 0),
            (self.eve.REG_PCLK, 5),
        ]
        for (adress, value) in setup:
            self.cmd_regwrite(adress, value)

    def setup_640x480(self):
        """Default setting for LCD 640x480"""
        self.Clear()
        self.swap()
        setup = [
            # (self.eve.REG_OUTBITS, 0),
            (self.eve.REG_DITHER, 0),
            (self.eve.REG_CSPREAD, 0),
            (self.eve.REG_PCLK_POL, 0),
            (self.eve.REG_ADAPTIVE_FRAMERATE, 0),

            (self.eve.REG_HCYCLE, 800),
            (self.eve.REG_HOFFSET, 16 + 96),
            (self.eve.REG_HSIZE, 640),

            (self.eve.REG_HSYNC1, 0),
            (self.eve.REG_HSYNC0, 96),

            (self.eve.REG_VCYCLE, 525),
            (self.eve.REG_VOFFSET, 12),
            (self.eve.REG_VSIZE, 480),

            (self.eve.REG_VSYNC1, 0),
            (self.eve.REG_VSYNC0, 10),
            (self.eve.REG_PCLK, 3),
        ]
        for (adress, value) in setup:
            self.cmd_regwrite(adress, value)
    def setup_800x480(self):
        """Default setting for LCD WVGA 800x480"""
        self.Clear()
        self.swap()
        setup = [
            # (self.eve.REG_OUTBITS, 0),
            (self.eve.REG_DITHER, 1),
            (self.eve.REG_CSPREAD, 0),
            (self.eve.REG_PCLK_POL, 1),
#            (self.eve.REG_ADAPTIVE_FRAMERATE, 0),

            (self.eve.REG_HCYCLE, 928),
            (self.eve.REG_HOFFSET, 88),
            (self.eve.REG_HSIZE, 800),

            (self.eve.REG_HSYNC1, 48),
            (self.eve.REG_HSYNC0, 0),

            (self.eve.REG_VCYCLE, 525),
            (self.eve.REG_VOFFSET, 32),
            (self.eve.REG_VSIZE, 480),

            (self.eve.REG_VSYNC1, 3),
            (self.eve.REG_VSYNC0, 0),
            (self.eve.REG_PCLK, 2),
        ]
        for (adress, value) in setup:
            self.cmd_regwrite(adress, value)
    def setup_800x480_NoSquare(self):
        """Default setting for LCD WVGA 800x480"""
        print("setup_800x480_NoSquare ")
        self.Clear()
        self.swap()
        setup = [
            # (self.eve.REG_OUTBITS, 0),
            (self.eve.REG_DITHER, 1),
            (self.eve.REG_CSPREAD, 0),
            (self.eve.REG_PCLK_POL, 1),
#            (self.eve.REG_ADAPTIVE_FRAMERATE, 0),

            (self.eve.REG_HCYCLE, 928),
            (self.eve.REG_HOFFSET, 88),
            (self.eve.REG_HSIZE, 861),
            (self.eve.REG_HSYNC1, 48),
            (self.eve.REG_HSYNC0, 0),

            (self.eve.REG_VCYCLE, 525),
            (self.eve.REG_VOFFSET, 32),
            (self.eve.REG_VSIZE, 480),

            (self.eve.REG_VSYNC1, 3),
            (self.eve.REG_VSYNC0, 0),
            #(self.eve.REG_PCLK, 2),
            (self.eve.REG_PCLK, 1), #When REG_PCLK is set to 1, the display output will be in EXTSYNC mode
            (self.eve.REG_PCLK_FREQ, 0x8A1), #60M
            #(self.eve.REG_PCLK_FREQ, 0x8B2), #33M
            #(self.eve.REG_PCLK_FREQ, 443),  #8M blink
        ]
        for (adress, value) in setup:
            self.cmd_regwrite(adress, value)

    def setup_1024x600(self):
        """Default setting for LCD WSVGA 1024x600"""
        self.Clear()
        self.swap()
        setup = [
            (self.eve.REG_DITHER, 1),
            (self.eve.REG_CSPREAD, 0),
            (self.eve.REG_PCLK_POL, 1),
            (self.eve.REG_ADAPTIVE_FRAMERATE, 0),

            (self.eve.REG_HCYCLE, 1344),
            (self.eve.REG_HOFFSET, 160),
            (self.eve.REG_HSIZE, 1024),

            (self.eve.REG_HSYNC1, 100),
            (self.eve.REG_HSYNC0, 0),

            (self.eve.REG_VCYCLE, 635),
            (self.eve.REG_VOFFSET, 23),
            (self.eve.REG_VSIZE, 600),

            (self.eve.REG_VSYNC1, 10),
            (self.eve.REG_VSYNC0, 0),
            (self.eve.REG_PCLK, 1),
            (self.eve.REG_PCLK_FREQ, 0xD12),
        ]
        for (adress, value) in setup:
            self.cmd_regwrite(adress, value)
    def setup_480x272(self):
        """Default setting for LCD WQVGA 480x272"""
        self.Clear()
        self.swap()
        setup = [
            (self.eve.REG_DITHER, 0),
            (self.eve.REG_CSPREAD, 0),
            (self.eve.REG_PCLK_POL, 1),

            (self.eve.REG_HCYCLE, 548),
            (self.eve.REG_HOFFSET, 43),
            (self.eve.REG_HSIZE, 480),

            (self.eve.REG_HSYNC1, 41),
            (self.eve.REG_HSYNC0, 0),

            (self.eve.REG_VCYCLE, 292),
            (self.eve.REG_VOFFSET, 12),
            (self.eve.REG_VSIZE, 272),

            (self.eve.REG_VSYNC1, 10),
            (self.eve.REG_VSYNC0, 0),
            (self.eve.REG_PCLK, 5),
        ]
        for (adress, value) in setup:
            self.cmd_regwrite(adress, value)

    def setup_480x128(self):
        """Default setting for LCD WQVGA 480x128"""
        self.Clear()
        self.swap()
        # Timings from: <https://github.com/crystalfontz/CFA480128Ex-039Tx/blob/master/CFA10099/CFA480128Ex_039Tx.h>
        setup = [
            (self.eve.REG_DITHER, 0),
            (self.eve.REG_CSPREAD, 0),
            (self.eve.REG_PCLK_POL, 1),

            (self.eve.REG_HCYCLE, 1042),
            (self.eve.REG_HOFFSET, 41),
            (self.eve.REG_HSIZE, 480),

            (self.eve.REG_HSYNC1, 35),
            (self.eve.REG_HSYNC0, 24),

            (self.eve.REG_VCYCLE, 137),
            (self.eve.REG_VOFFSET, 8),
            (self.eve.REG_VSIZE, 128),

            (self.eve.REG_VSYNC1, 5),
            (self.eve.REG_VSYNC0, 4),
            (self.eve.REG_PCLK, 7),
        ]
        for (adress, value) in setup:
            self.cmd_regwrite(adress, value)

    def setup_1280x800(self):
        """Default setting for LCD WXGA 1280x800"""
        self.Clear()
        self.swap()
        setup = [
            (self.eve.REG_OUTBITS, 0),
            (self.eve.REG_PCLK, 0),
            (self.eve.REG_DITHER, 0),
            (self.eve.REG_CSPREAD, 0),
            (self.eve.REG_PCLK_POL, 0),
            (self.eve.REG_PCLK_2X, 0),

            (self.eve.REG_HCYCLE, 1411),
            (self.eve.REG_HOFFSET, 120),
            (self.eve.REG_HSIZE, 1280),

            (self.eve.REG_HSYNC1, 100),
            (self.eve.REG_HSYNC0, 0),

            (self.eve.REG_VCYCLE, 815),
            (self.eve.REG_VOFFSET, 14),
            (self.eve.REG_VSIZE, 800),

            (self.eve.REG_VSYNC1, 10),
            (self.eve.REG_VSYNC0, 0),
            (self.eve.REG_PCLK_FREQ, 0x8B1),
            (self.eve.REG_PCLK, 1),
        ]
        for (adress, value) in setup:
            self.cmd_regwrite(adress, value)

    # Some higher-level functions
    def get_inputs(self):
        """Get user inputs"""
        self.finish()
        touch = _Touch(*struct.unpack("HHIhhhhB",
            self.transfer_read(self.eve.REG_TOUCH_RAW_XY, 17)))

        tracker = _Tracker(*struct.unpack("HH", self.transfer_read(self.eve.REG_TRACKER, 4)))

        if not hasattr(self, "prev_touching"):
            self.prev_touching = False
        touching = (touch.x != -32768)
        press = touching and not self.prev_touching
        release = (not touching) and self.prev_touching
        state = _State(touching, press, release)
        self.prev_touching = touching

        self.inputs = _Inputs(touch, tracker, state)
        return self.inputs

    def swap(self):
        """Flush command queue and swap display list"""
        self.Display()
        self.eve.cmd_swap()
        self.flush()
        self.eve.cmd_dlstart()
        self.eve.cmd_loadidentity()

    def calibrate(self):
        """Start calibration screen"""
        self.ClearColorRGB(64, 64, 64)
        self.Clear(1, 1, 1)
        self.ColorRGB(0xff, 0xff, 0xff)
        self.eve.cmd_text(self.lcd_width // 2, self.lcd_height // 2, 29, 0x0600, "Tap the dot")

        self.eve.cmd_calibrate()
        self.eve.cmd_dlstart()

    def screenshot_ft800(self, dest):
        """Take screen shot, this function is only available on FT800"""
        self.finish()

        pclk = self.rd32(self.eve.REG_PCLK)
        self.wr32(self.eve.REG_PCLK, 0)
        time.sleep(0.001)
        self.wr32(self.eve.REG_SCREENSHOT_EN, 1)
        self.wr32(0x0030201c, 32)

        for i in range(self.lcd_height):
            print(i, "/", self.lcd_height)
            self.wr32(self.eve.REG_SCREENSHOT_Y, i)
            self.wr32(self.eve.REG_SCREENSHOT_START, 1)
            time.sleep(.002)

            while self.transfer_read(self.eve.REG_SCREENSHOT_BUSY, 8) != bytes(8):
                pass

            self.wr32(self.eve.REG_SCREENSHOT_READ, 1)
            bgra = self.transfer_read(self.eve.RAM_SCREENSHOT, 4 * self.lcd_width)
            (color_b, color_g, color_r) = [bgra[i::4] for i in range(3)]
            line = bytes(sum(zip(color_r, color_g, color_b), ()))
            dest(line)
            self.wr32(self.eve.REG_SCREENSHOT_READ, 0)
        self.wr32(self.eve.REG_SCREENSHOT_EN, 0)
        self.wr32(self.eve.REG_PCLK, pclk)

    def load(self, file_handler):
        """Load a file to command fifo"""
        while True:
            chunk = file_handler.read(512)
            if not chunk:
                return
            self.cc(align4(chunk))
