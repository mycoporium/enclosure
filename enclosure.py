# Thread: Queued data submissions to API, receive configuration updates
# Thread: SCD-30 sampling
# Thread: Take pictures
# Main: Set shift-register patterns

import os
import sys
import time
import signal
import logging
import argparse
import configparser

import multiprocessing as mp

from datetime import datetime
from multiprocessing import Process, Queue
from scd30_i2c import SCD30

from shift_reg import ShiftRegister


def take_picture(config):

    IMG_DIR = os.path.abspath(config['images_dir'])

    img_count = len(os.listdir(IMG_DIR))
    zlen = len(str(img_count))

    logging.info('Starting pictures...')

    while True:

        if len(str(img_count)) > zlen:
            zlen += 1
            for fn in os.listdir(IMG_DIR):
                num = fn.split('_')[1].split('.')[0].zfill(zlen)
                new_fn = os.path.join(IMG_DIR, f'image_{num}.jpg')
                old_fn = os.path.join(IMG_DIR, fn)
                os.rename(old_fn, new_fn)

        fc = str(img_count).zfill(zlen)
        fn = os.path.join(IMG_DIR, f'image_{fc}.jpg')

        logging.info('Capturing %s', fn)
        os.system(f'libcamera-still -o {fn} -v 0 --immediate --vflip --hflip')

        img_count += 1
        time.sleep(60)


def read_air(data_cue, config):

    DATA_FILE = os.path.abspath(config['air_data_log'])

    # SDC30 class uses I²C pins by default, it seems. Works without telling it which pins to use.
    #DATA_PIN = config['sdc_data']
    #CLOCK_PIN = config['sdc_clock']
    #READY_PIN = config['sdc_ready']
    #VOUT_PIN = config['sdc_vout']

    scd30 = SCD30()

    scd30.set_measurement_interval(2)
    scd30.start_periodic_measurement()

    time.sleep(2)

    f = open(DATA_FILE, 'a', encoding='utf-8')

    while True:

        try:
            ready = scd30.get_data_ready()
        except OSError as exc:
            logging.error('Sensor NOT READY: %s', exc)
            logging.exception('Sensor NOT READY: %s', exc)
            ready = False

        if ready:
            m = scd30.read_measurement()
            if m is not None:
                send_list = list(m)
                data_cue.put(send_list)
                timestamp = datetime.now().strftime('%d %b %Y %H:%M:%S')

                log_data = f'{timestamp} CO2: {m[0]:.2f}ppm, temp: {m[1]:.2f}°C, rh: {m[2]:.2f}%\n'
                f.write(log_data)
                f.flush()

            time.sleep(2)
        else:
            time.sleep(0.2)

    f.close()


def shutdown(sig, frame):

    logging.debug('Signal: %s', sig)
    logging.debug('Frame: %s', frame)

    sr.set_bits('00000000')
    sys.exit(0)


def parse_args():

    root = argparse.ArgumentParser(prog='enclosure.py')
    root.add_argument('--log-level', '-l', action='store', help='Log level per python logging module', default='INFO', choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL'], required=False)
    root.add_argument('--config', '-c', action='store', help='Location of the config file', default='/etc/enclosure/enclosure.conf', required=False)

    args = root.parse_args()

    return args


def parse_config(path, section=None):

    config = configparser.ConfigParser()
    config.read(path)

    if section is not None:
        conf = config[section]
        return conf

    return config


if __name__ == '__main__':

    args = parse_args()

    gconf = parse_config(args.config, 'global')
    profile = parse_config(gconf['profile'], 'env')
    outlets = parse_config(args.config, 'outlets')
    pins = parse_config(args.config, 'pins')

    log_level = getattr(logging, args.log_level)

    logging.basicConfig(
            level=log_level,
            filename=gconf['monitor_log'],
            format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s',
            datefmt='%d-%b-%Y %H:%M:%S'
    )

    logging.info('Starting...')

    count = mp.cpu_count()

    logging.info('CPUs: %s', count)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Blue oyster profile
    MAX_CO2 = int(profile['CO2_MAX'])
    MIN_CO2 = int(profile['CO2_MIN'])

    MAX_HUM = int(profile['HUM_MAX'])
    MIN_HUM = int(profile['HUM_MIN'])

    MAX_TMP = int(profile['TEMP_MAX'])
    MIN_TMP = int(profile['TEMP_MIN'])

    MAX_LGT = int(profile['LIGHT_MAX'])
    MIN_LGT = int(profile['LIGHT_MIN'])

    HUM_OUTLET = int(outlets['humidifier'])
    HTR_OUTLET = int(outlets['heater'])
    LGT_OUTLET = int(outlets['light'])
    FAN_OUTLET = int(outlets['fan'])

    CLOCK_PIN = int(pins['sr_clock'])
    LATCH_PIN = int(pins['sr_latch'])
    DATA_PIN = int(pins['sr_data'])

    sr = ShiftRegister(clock=CLOCK_PIN, latch=LATCH_PIN, data=DATA_PIN)

    data_q = Queue(-1)

    pic_proc = Process(target=take_picture, args=(gconf,))
    pic_proc.daemon = True
    pic_proc.start()

    air_proc = Process(target=read_air, args=(data_q, gconf))
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

