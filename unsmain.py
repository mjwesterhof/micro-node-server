#!/usr/bin/env micropython

# = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = #
#                                                                             #
# unsmain.py - test script for ESP8266-based micro-node-server                #
#                                                                             #
# = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = #
#
# MIT License
#
# Copyright (c) 2017 Mike Westerhof
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = #

import dht
import gc
import machine
import utime as time
from unslib import *

# = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = #

class HandleIO():

    _ioq = None
    _restq = None

    _success = True

    _ticks = None
    _secs  = None
    _dsecs = None
    _mins  = None
    _9mins = None

    _drivers = {'ST' : [0, 51, None],  # Percentage
                'GV1': [0,  2, None],  # On/Off
                'GV2': [0,  2, None],  # On/Off
                'GV3': [0,  2, None],  # On/Off
                'GV4': [0,  2, None],  # On/Off
                'GV5': [0, 56, None],  # Int8
                'GV6': [0, 56, None],  # Int8
                'GV7': [0, 56, None],  # Int8
                'GV8': [0, 56, None],  # Int8
                'GV9': [0, 56, None]}  # Int32
    _led1 = None
    _led2 = None
    _dht = None
    _btn = None

    _btn_value = 0
    _btn_on = False
    _send_btn_command = False

    _debug = 0

    def __init__(self, ioq, restq, debug=0):
        self._restq = restq
        self._ioq = ioq
        self._debug = debug
        self._led1 = machine.PWM(machine.Pin(15), freq=1000)
        self._led1.duty(0)
        self._led2 = machine.Pin(2, machine.Pin.OUT)
        self._led2.value(0)
        self._dht = dht.DHT11(machine.Pin(4))
        self._btn = machine.Pin(12, machine.Pin.IN, machine.Pin.PULL_UP)
        
    def run(self):
        # Start by handling the input queue
        if self._ioq:
            inp = self._ioq.pop(0)
            if self._debug > 0:
                print("IO: input operation:", inp)
            if inp == b"S":
                self._hdl_qs(False)
            elif inp == b"Q":
                self._hdl_qs(True)
            elif inp == b"A":
                self._hdl_add()
            elif inp[0] == 47:  # b"/"
                self._hdl_cmd(inp)
            elif inp[0] == 82:  # b"R"
                # TODO: correctly handle response
                self._hdl_rid(inp)
            else:
                print("IO: Error: unknown request", inp[0])

        # Update the ISY on startup
        if self._ticks is None:
            self._hdl_qs(False)

        # Handle I/O devices no more often than every 10ms
        ticks = time.ticks_ms()
        if self._ticks is None or (time.ticks_diff(ticks, self._ticks) > 10):
            self._ticks = ticks
            b = self._btn.value()
            if b != self._btn_value:
                # We have a button state change
                if b == 0:
                    # Button changed to "pressed"
                    if self._debug > 1:
                        print("IO: button pressed, sending command...")
                    self._send_btn_command = True
                self._btn_value = b

        # Handle 1s I/O pin polling here... (995ms to stagger events)
        if self._secs is None or (time.ticks_diff(ticks, self._secs) > 995):
            self._secs = ticks
            if self._send_btn_command:
                self._send_btn_command = False
                p = b"/rest/ns/3/nodes/n003_esp/report/cmd/CA"
                self._restq.append(p)
                
        # Handle 10s I/O pin polling here... (stagger +103ms here)
        if self._dsecs is None or (time.ticks_diff(ticks, self._dsecs) > 10103):
            self._dsecs = ticks
            self._read_dht(send_report=True)

        # Handle 60s I/O pin polling here... (stagger +207 ms)
        if self._mins is None or (time.ticks_diff(ticks, self._mins) > 60207):
            self._mins = ticks

        # Handle 9m Heartbeat polling here... (stagger -333 ms)
        if self._9mins is None or (time.ticks_diff(ticks, self._9mins) > ((60000*9)-333)):
            self._9mins = ticks
            p = b"/rest/ns/3/nodes/n003_esp/report/cmd/CB"
            self._restq.append(p)

        # Set LED1 based on the command
        self._led1.duty(int(self._drivers['ST'][0] * 10.23))

        # Set LED2 based on the command
        self._led2.value(self._drivers['GV1'][0])

    def _read_dht(self, send_report=False):
        self._dht.measure()
        self._drivers['GV6'][0] = int(((self._dht.temperature()*9)/5)+32)
        self._drivers['GV7'][0] = self._dht.humidity()
        if send_report:
            self._report('GV6')
            self._report('GV7')

    def _hdl_qs(self, is_query):
        if is_query:
            self._read_dht(send_report=False)
        for key in self._drivers.keys():
            self._report(key, force=is_query)
        
    def _report(self, k, force=False):
        v = self._drivers[k][0]
        o = self._drivers[k][2]
        if (force) or (o is None) or (v != o):
            u = self._drivers[k][1]
            p = b"/rest/ns/3/nodes/n003_esp/report/status/{}/{}/{}".format(k,v,u)
            if self._debug > 1:
                print("IO: _report: restq.append({})".format(p))
            self._restq.append(p)
            self._drivers[k][2] = v

    def _hdl_add(self):
        p = b"/rest/ns/3/nodes/n003_esp/add/ESP_MAIN?primary=n003_esp&name=esp8266"
        self._restq.append(p)

    def _hdl_rid(self, inp):
        rid = inp[1:]
        # [TODO] figure out how to handle success/fail...
        if self._success:
            p = b"/rest/ns/3/report/request/" + rid + b"/success"
        else:
            p = b"/rest/ns/3/report/request/" + rid + b"/failed"
        if self._debug > 1:
            print("IO: _rid: restq.append({})".format(p))
        self._restq.append(p)

    def _hdl_cmd(self, inp):
        cl = inp.split(b"/")
        cm = cl[1]
        if self._debug > 0:
            print('IO: command is {}'.format(cm))
        report = None
        if cm == b'C1':
            if self._drivers['ST'][0] < 100:
                self._drivers['ST'][0] += 1
                report = 'ST'
        elif cm == b'C2':
            if self._drivers['ST'][0] > 0:
                self._drivers['ST'][0] -= 1
                report = 'ST'
        elif cm == b'C3':
            self._drivers['GV1'][0] = 1
            report = 'GV1'
        elif cm == b'C4':
            self._drivers['GV1'][0] = 0
            report = 'GV1'
        elif cm == b'DOF':
            self._drivers['ST'][0] = 0
            report = 'ST'
        elif cm == b'DON':
            if len(cl) > 2:
                self._drivers['ST'][0] = int(cl[2])
            else:
                self._drivers['ST'][0] = 100
            report = 'ST'

        # Send report for affected driver value
        if report is not None:
            self._report(report)

# = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = #

debug = 1

ioq = []
restq = []

io_handler = HandleIO(ioq, restq, debug=debug)
rest_server = StateMachineServer(ioq, 8300, debug=debug)
rest_client = StateMachineClient(restq, b"192.168.1.200",
                                 b"192.168.1.62", 80,
                                 b"your-base64-encoded-id-pw-string",
                                 debug=debug)

tcks = None
freemem = 0

gc.collect()

try:
    while True:
        rest_server.run(limit=1000)
        rest_client.run(limit=1000)
        io_handler.run()

        gc.collect()

        if debug > 0:
            now = time.ticks_ms()
            if (tcks is None) or (time.ticks_diff(now, tcks) > 60000):
                f = gc.mem_free()
                if f != freemem:
                    print("Free memory:", f)
                    freemem = f
                tcks = now

except KeyboardInterrupt:
    print("Exiting...")

# = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = #
# = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = #
