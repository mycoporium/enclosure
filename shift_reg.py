import time
import logging

from gpiozero import LED

# https://www.youtube.com/watch?v=ameNT2MKDyE
# https://youtu.be/2KaeHWGd2JA

class ShiftRegister:

    def __init__(self, data, clock, latch):
        """When you pulse RCLK, whatever values are in the shift register will be
           output to the pins.

        """

        self.DTA_PIN = data  # SER
        self.CLK_PIN = clock # SRCLK
        self.LTC_PIN = latch # RCLK

        self.DTA = LED(self.DTA_PIN)
        self.CLK = LED(self.CLK_PIN)
        self.LTC = LED(self.LTC_PIN)


    def clear_outputs(self):
        """This can also be done by pulling the SRCLR pin to low, but in most
           examples, this pin is wired to VCC and therefore unused.
        """

        for _ in range(8):
            self.shift_value(False)

        self.pulse_latch()


    def pulse_latch(self):

        self.LTC.on()
        self.LTC.off()


    def pulse_clock(self):

        self.CLK.on()
        self.CLK.off()


    def shift_value(self, bit: bool):

        if bit is True:
            self.DTA.on()

        if bit is False:
            self.DTA.off()

        self.pulse_clock()


    def set_bits(self, bit_str):
        logging.info(f'Setting register bits to {bit_str}')

        for bit in bit_str:

            if bit == '1':
                self.shift_value(True)
            if bit == '0':
                self.shift_value(False)

        self.pulse_latch()
