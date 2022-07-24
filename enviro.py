#!/usr/bin/env python3
# -*- python -*-

"""Munin plugin to monitor environmental data.
=pod

=head1 NAME

enviro - monitor enviro status

=head1 CONFIGURATION

Following config is needed:

[enviro]
user root

=head1 AUTHOR

dpse

=head1 LICENSE

GPLv2

=head1 MAGIC MARKERS

#%# family=auto
#%# capabilities=autoconf

=cut
"""

import os
import subprocess
import sys

import time

from bme280 import BME280

try:
    from smbus2 import SMBus
except ImportError:
    from smbus import SMBus

try:
    # Transitional fix for breaking change in LTR559
    from ltr559 import LTR559

    ltr559 = LTR559()
except ImportError:
    import ltr559

from enviroplus import gas
from enviroplus.noise import Noise

bus = SMBus(1)
bme280 = BME280(i2c_dev=bus)
noise = Noise()

# Number of samples to take per measurement
samples = 10


def get_cpu_temperature():
    with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
        temp = f.read()
        temp = int(temp) / 1000.0
    return temp


def avg(values):
    return sum(values) / float(len(values))


def sample(func):
    values = [func()] * samples
    for i in range(samples):
        time.sleep(0.1)
        values = values[1:] + [func()]
    return avg(values)


def correct_temperature(temperature, cpu_temperature):
    return temperature - ((cpu_temperature - temperature) / 2.25)


def correct_humidity(humidity, temperature, corr_temperature):
    dewpoint = temperature - ((100 - humidity) / 5)
    corr_humidity = 100 - (5 * (corr_temperature - dewpoint))
    return min(100, corr_humidity)


def read_init():
    bme280.update_sensor()
    ltr559.get_lux()
    gas.read_all()
    noise.get_noise_profile()
    time.sleep(0.5)


def read_bme280():
    cpu_temps = [get_cpu_temperature()] * samples
    raw_temps = [bme280.get_temperature()] * samples
    raw_humids = [bme280.get_humidity()] * samples
    for i in range(samples):
        time.sleep(0.1)
        cpu_temps = cpu_temps[1:] + [get_cpu_temperature()]
        raw_temps = raw_temps[1:] + [bme280.get_temperature()]
        raw_humids = raw_humids[1:] + [bme280.get_humidity()]
    cpu_temp = avg(cpu_temps)
    temp = avg(raw_temps)
    humid = avg(raw_humids)
    temp_corr = correct_temperature(temp, cpu_temp)
    humid_corr = correct_humidity(humid, temp, temp_corr)
    pressure = sample(bme280.get_pressure)
    altitude = sample(bme280.get_altitude)
    return {'temperature': temp_corr,
            'humidity': humid_corr,
            'pressure': pressure,
            'altitude': altitude,
            'cpu_temperature': cpu_temp,
            'raw_temperature': temp,
            'raw_humidity': humid}


def read_ltr559():
    light = sample(ltr559.get_lux)
    return {'light': light}


def read_gas():
    gas.read_all()
    time.sleep(0.2)
    data = gas.read_all()
    ox = [data.oxidising / 1000] * samples
    re = [data.reducing / 1000] * samples
    nh = [data.nh3 / 1000] * samples
    for i in range(samples):
        time.sleep(0.1)
        data = gas.read_all()
        ox = ox[1:] + [data.oxidising / 1000]
        re = re[1:] + [data.reducing / 1000]
        nh = nh[1:] + [data.nh3 / 1000]
    oxidising = avg(ox)
    reducing = avg(re)
    nh3 = avg(nh)
    return {'oxidising': oxidising,
            'reducing': reducing,
            'nh3': nh3}


def read_noise():
    low, mid, high, amp = noise.get_noise_profile()
    lows = [low] * samples
    mids = [mid] * samples
    highs = [high] * samples
    amps = [amp] * samples
    for i in range(samples):
        time.sleep(0.1)
        low, mid, high, amp = noise.get_noise_profile()
        lows = lows[1:] + [low]
        mids = mids[1:] + [mid]
        highs = highs[1:] + [high]
        amps = amps[1:] + [amp]
    low = avg(lows)
    mid = avg(mids)
    high = avg(highs)
    amp = avg(amps)
    return {'low': low,
            'mid': mid,
            'high': high,
            'amp': amp}


def print_graph(key):
    print('multigraph enviro_{}'.format(key))


def print_value(data, key):
    print('{}.value {:.8f}'.format(key, data[key]))


def print_graph_value(data, key):
    print_graph(key)
    print_value(data, key)
    print('')


def fetch():
    read_init()
    data = {}
    data.update(read_bme280())
    data.update(read_ltr559())
    data.update(read_gas())
    data.update(read_noise())

    print_graph('temperature')
    print_value(data, 'temperature')
    print_value(data, 'raw_temperature')
    print_value(data, 'cpu_temperature')
    print('')

    print_graph('humidity')
    print_value(data, 'humidity')
    print_value(data, 'raw_humidity')
    print('')

    print_graph_value(data, 'pressure')

    print_graph_value(data, 'altitude')

    print_graph_value(data, 'light')

    print_graph('gas')
    print_value(data, 'oxidising')
    print_value(data, 'reducing')
    print_value(data, 'nh3')
    print('')

    print_graph('noise')
    print_value(data, 'low')
    print_value(data, 'mid')
    print_value(data, 'high')
    print_value(data, 'amp')


def print_graph_config(key, title, vlabel, zero_limit=False):
    print('multigraph enviro_{}'.format(key))
    print('graph_title {}'.format(title))
    print('graph_vlabel {}'.format(vlabel))
    print('graph_category environment')
    if zero_limit:
        print('graph_args --base 1000 --lower-limit 0')
    else:
        print('graph_args --base 1000')


def print_value_config(key, title):
    print('{}.label {}'.format(key, title))


def config():
    print_graph_config('temperature', 'Temperature', 'C')
    print_value_config('temperature', 'Temperature')
    print_value_config('raw_temperature', 'Raw Temperature')
    print_value_config('cpu_temperature', 'CPU Temperature')
    print('')
    print_graph_config('humidity', 'Humidity', '%RH')
    print_value_config('humidity', 'Humidity')
    print_value_config('raw_humidity', 'Raw Humidity')
    print('')
    print_graph_config('pressure', 'Pressure', 'hPa')
    print_value_config('pressure', 'Pressure')
    print('')
    print_graph_config('altitude', 'Altitude', 'm')
    print_value_config('altitude', 'Altitude')
    print('')
    print_graph_config('light', 'Light', 'Lux')
    print_value_config('light', 'Light')
    print('')
    print_graph_config('gas', 'Gas', 'kO')
    print_value_config('oxidising', 'Oxidising')
    print_value_config('reducing', 'Reducing')
    print_value_config('nh3', 'NH3')
    print('')
    print_graph_config('noise', 'Noise', 'amp')
    print_value_config('low', 'Low')
    print_value_config('mid', 'Mid')
    print_value_config('high', 'High')
    print_value_config('amp', 'Amp')
    print('')

    if os.environ.get('MUNIN_CAP_DIRTYCONFIG') == '1':
        fetch()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'autoconf':
        print('yes')
    elif len(sys.argv) > 1 and sys.argv[1] == 'config':
        config()
    else:
        fetch()

exit(0)
