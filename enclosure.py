# Thread: Queued data submissions to API, receive configuration updates
# Thread: SCD-30 sampling
# Thread: Take pictures
# Main: Set shift-register patterns

import os
import sys
import time
import signal
import logging
import multiprocessing as mp

from datetime import datetime
from multiprocessing import Process, Queue
from gpiozero import LED
from scd30_i2c import SCD30

from shift_reg import ShiftRegister

BASE_PATH = os.path.abspath('/media/asustor/MushroomFarm')
MON_LOG = os.path.join(BASE_PATH, 'data', 'monitor.log')

logging.basicConfig(
        level=logging.INFO,
        filename=MON_LOG,
        format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s',
        datefmt='%d-%b-%Y %H:%M:%S'
)

count = mp.cpu_count()
logging.info(f'CPUs: {count}')


def take_picture():

    IMG_DIR = os.path.join(BASE_PATH, 'data', 'images')

    count = len(os.listdir(IMG_DIR))
    zlen = len(str(count))

    logging.info('Starting pictures...')

    while True:

        if len(str(count)) > zlen:
            zlen += 1
            for fn in os.listdir(IMG_DIR):
                num = fn.split('_')[1].split('.')[0].zfill(zlen)
                new_fn = os.path.join(IMG_DIR, f'image_{num}.jpg')
                old_fn = os.path.join(IMG_DIR, fn)
                os.rename(old_fn, new_fn)

        fc = str(count).zfill(zlen)
        fn = os.path.join(IMG_DIR, f'image_{count}.jpg')

        logging.info(f'Capturing {fn}')
        os.system(f'libcamera-still -o {fn} -v 0 --immediate --vflip --hflip')

        count += 1
        time.sleep(60)


def read_air(data_cue):

    DATA_FILE = os.path.join(BASE_PATH, 'data', 'air_data.log')

    DATA_PIN = 2
    CLOCK_PIN = 3
    READY_PIN = 17
    V3OUT_PIN = 27

    scd30 = SCD30()

    scd30.set_measurement_interval(2)
    scd30.start_periodic_measurement()

    time.sleep(2)

    while True:
        if scd30.get_data_ready():
            m = scd30.read_measurement()
            if m is not None:
                send_list = list(m)
                data_cue.put(send_list)
                timestamp = datetime.now().strftime('%d %b %Y %H:%M:%S')

                log_data = f'{timestamp} CO2: {m[0]:.2f}ppm, temp: {m[1]:.2f}°C, rh: {m[2]:.2f}%\n'
                with open(DATA_FILE, 'a') as f:
                    f.write(log_data)

            time.sleep(2)
        else:
            time.sleep(0.2)


def shutdown(sig, frame):

    sr.set_bits('00000000')
    sys.exit(0)


if __name__ == '__main__':

    logging.info('Starting...')

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Blue oyster profile
    MAX_CO2 = 1000
    MIN_CO2 = 500

    # Primordia = 95-100
    # Fruits = 85-95
    MAX_HUM = 95 # Guessing 100 is impossible to reach
    MIN_HUM = 85

    MAX_TMP = 24
    MIN_TMP = 13

    MAX_LGT = 18
    MIN_LGT = 6

    # Outlets are zero-indexed
    HUM_OUTLET = 7
    HTR_OUTLET = 5
    LGT_OUTLET = 3
    FAN_OUTLET = 6

    CLOCK_PIN = 23
    LATCH_PIN = 24
    DATA_PIN = 25

    sr = ShiftRegister(clock=CLOCK_PIN, latch=LATCH_PIN, data=DATA_PIN)

    data_q = Queue(-1)

    pic_proc = Process(target=take_picture)
    pic_proc.daemon = True
    pic_proc.start()

    air_proc = Process(target=read_air, args=(data_q,))
    air_proc.daemon = True
    air_proc.start()

    bits = '00000000'
    sr.clear_outputs()

    while True:

        bit_list = list(bits)

        air_data = data_q.get()
        co2 = round(air_data[0], 1)
        temp = round(air_data[1], 1)
        rh = round(air_data[2], 1)

        # Lights
        now = datetime.now().timetuple()
        if now.tm_hour >= MIN_LGT and now.tm_hour < MAX_LGT and bits[LGT_OUTLET] == '0':
            logging.info('TIME is DAY (%s <= %s < %s), turning ON outlet %s (lights)', MIN_LGT, now.tm_hour, MAX_LGT, LGT_OUTLET)
            bit_list[LGT_OUTLET] = 1
        elif (now.tm_hour < MIN_LGT or now.tm_hour >= MAX_LGT) and bits[LGT_OUTLET] == '1':
            logging.info('TIME is NIGHT (%s <= %s < %s), turning OFF outlet %s (lights)', MIN_LGT, now.tm_hour, MAX_LGT, LGT_OUTLET)
            bit_list[LGT_OUTLET] = 0

        # Humidifier
        if rh >= MAX_HUM and bits[HUM_OUTLET] == '1':
            logging.info('HUM is HIGH (%s >= %s), turning OFF outlet %s (humidifier)', rh, MAX_HUM, HUM_OUTLET)
            bit_list[HUM_OUTLET] = 0
        elif rh < MIN_HUM and bits[HUM_OUTLET] == '0':
            logging.info('HUM is LOW  (%s <= %s), turning ON outlet %s (humidifier)', rh, MIN_HUM, HUM_OUTLET)
            bit_list[HUM_OUTLET] = 1

        # Fan - on if co2 is too high, low hum and low temp don't matter
        #     - on if temp too high, co2 and hum don't matter
        #     - off if temp or hum less than max
        if (co2 >= MAX_CO2 or temp >= MAX_TMP) and bits[FAN_OUTLET] == '0':
            if co2 >= MAX_CO2:
                logging.info('CO2 is HIGH (%s >= %s), turning ON outlet %s (fan)', co2, MAX_CO2, FAN_OUTLET)
            if temp >= MAX_TMP:
                logging.info('TMP is HIGH (%s >= %s), turning ON outlet %s (fan)', temp, MAX_TMP, FAN_OUTLET)
            bit_list[FAN_OUTLET] = 1
        elif (temp <= MIN_TMP) and bits[FAN_OUTLET] == '1':
            if temp <= MIN_TMP:
                logging.info('TMP is LOW  (%s >= %s), turning OFF outlet %s (fan)', temp, MIN_TMP, FAN_OUTLET)
            bit_list[FAN_OUTLET] = 0

        # Heater
        if (temp >= MAX_TMP) and bits[HTR_OUTLET] == '1':
            logging.info('TMP is HIGH (%s >= %s), turning OFF outlet %s (heater)', temp, MAX_TMP, HTR_OUTLET)
            bit_list[HTR_OUTLET] = 0
        elif (temp <= MIN_TMP) and bits[HTR_OUTLET] == '0':
            logging.info('TMP is LOW  (%s >= %s), turning ON outlet %s (heater)', temp, MIN_TMP, HTR_OUTLET)
            bit_list[HTR_OUTLET] = 1

        new_bits = ''.join(list(map(str, bit_list)))

        if new_bits != bits:
            bits = new_bits
            sr.set_bits(new_bits)

