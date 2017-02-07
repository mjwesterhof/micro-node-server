# unslib.py
#
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

import usocket as socket
import utime as time

# = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = #

class StateMachineServer():

    _next = None

    _sock = None
    _client_sock = None
    _ibuf = b""
    _obuf = b""

    _ioq = None

    _r200 = b"HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\nOK\r\n"
    _r404 = b"HTTP/1.0 404 ERROR\r\nContent-Type: text/plain\r\n\r\nERROR 404\r\n"

    _port = None

    _debug = 0

    def __init__(self, ioq, port, debug=0):
        self._next = self._open
        self._ioq = ioq
        self._port = port
        self._debug = debug
        
    def run(self, limit=0):
        have_work = True
        if limit > 0:
            start = time.ticks_us()
        while (True):
            # Execute the next state in the state machine
            have_work = self._next()
            # No more work?  No limit? Then we're done.
            if (not have_work) or not (limit > 0):
                break
            # More work, but check the time limit.
            now = time.ticks_us()
            delta = time.ticks_diff(now, start)
            if delta > limit:
                break
        return have_work

    def _err(self):
        try:
            if self._sock is not None:
                self._sock.close()
        except:
            pass
        try:
            if self._clientsock is not None:
                self._clientsock.close()
        except:
            pass
        self._ibuf = b""
        self._obuf = b""
        self._next = self._open
        return False
        
    def _open(self):
        addr = socket.getaddrinfo("0.0.0.0", self._port)[0][-1]
        self._sock = socket.socket()
        self._sock.setblocking(False)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(addr)
        self._sock.listen(1)
        if self._debug > 0:
            print("Server: Listening...")
        self._next = self._accept
        return True

    def _accept(self):
        have_work = False
        try:
            self._clientsock, addr = self._sock.accept()
            self._clientsock.setblocking(False)
            self._next = self._read
            have_work = True
        except OSError as e:
            if e.args[0] == 11:     # EAGAIN - operation would block
                pass
            elif e.args[0] == 110:  # ETIMEDOUT
                pass
            else:
                print("Server:", e)
                self._next = self._err
        return have_work

    def _read(self):
        have_work = False
        try:
            x = self._clientsock.recv(1024)
            if len(x) > 0:
                self._ibuf += x
                if self._ibuf.endswith(b"\r\n\r\n"):
                    self._next = self._process
                if self._debug > 1:
                    print("Server: Reading", x)
            else:
                print("Server: Error: client socket disconnected.")
                self._ibuf = b""
                self._next = self._close
            have_work = True
        except OSError as e:
            if e.args[0] == 11:     # EAGAIN - operation would block
                pass
            elif e.args[0] == 110:  # ETIMEDOUT
                pass
            else:
                print("Server:", e)
                self._next = self._err
        return have_work

    def _process(self):
        eol = self._ibuf.find(b"\r\n")
        tokens = self._ibuf[0:eol].split(b" ")
        if len(tokens) < 2:
            print("Server: Error: malformed request:", self._ibuf)
            self._ibuf = b""
            self._next = self._close
            return True
        if self._debug > 0:
            print("Server: Path:", tokens[1])
        self._ibuf = b""
        self._obuf = self._r200
        self._next = self._write
        path = tokens[1].split(b"?", 1)
        qs = b""
        if len(path) > 1:
            qs = path[1]
        path = path[0]

        # Edit out the node number - this is ugly; need a
        # better way to handle this.
        #
        # 0         1         2
        # 0123456789012345678901234
        # |           | |     |  |
        # /uns/nodes/n999_esp/query
        # /uns/nodes/n999_esp/cmd/
        # /uns/nodes/n_esp/cmd/
        # /uns/add/nodes
        path2 = path[0:12] + path[15:]
        if path == b"/uns/add/nodes":
            self._ioq.append(b"A")
        elif path2 == b"/uns/nodes/n_esp/query":
            self._ioq.append(b"Q")
        elif path2 == b"/uns/nodes/n_esp/status":
            self._ioq.append(b"S")
        elif path2 == b"/uns/nodes/n_esp/cmd/ST":
            self._ioq.append(b"S")
        elif path2.startswith(b"/uns/nodes/n_esp/cmd/"):
            self._ioq.append(path2[20:])
        else:
            self._obuf = self._r404
            return True

        parms = qs.split(b"&")
        for p in parms:
            if p:
                pl = p.split(b"=")
                if len(pl) > 1 and pl[0] == b"requestId":
                    self._ioq.append(b"R" + pl[1])
        return True

    def _write(self):
        have_work = False
        try:
            n = self._clientsock.send(self._obuf)
            if n  > 0:
                if n < len(self._obuf):
                    del self._obuf[0:n]
                else:
                    self._obuf = b""
                    self._next = self._close
                have_work = True
            else:
                print("Server: Error: nothing written to client...")
        except OSError as e:
            if e.args[0] == 11:     # EAGAIN - operation would block
                pass
            elif e.args[0] == 110:  # ETIMEDOUT
                pass
            else:
                print("Server:", e)
                self._next = self._err
        return have_work

    def _close(self):
        try:
            self._clientsock.close()
        except:
            pass
        self._ibuf = b""
        self._obuf = b""
        self._next = self._accept
        return True

# = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = #

class StateMachineClient():

    _next = None

    _sock = None
    _addr = None
    _ibuf = b""
    _obuf = b""
    _obufp = 0
    _rqst = None

    _restq = None

    _my_addr = None
    _isy_addr = None
    _isy_auth = None
    _isy_port = None

    _debug = 0

    def __init__(self, restq, my_addr, isy_addr, isy_port, isy_auth, debug=0):
        self._next = self._fetch
        self._restq = restq
        self._my_addr = my_addr
        self._isy_addr = isy_addr
        self._isy_port = isy_port
        self._isy_auth = isy_auth
        self._debug = debug
        
    def run(self, limit=0):
        have_work = True
        if limit > 0:
            start = time.ticks_us()
        while (True):
            # Execute the next state in the state machine
            have_work = self._next()
            # No more work?  No limit? Then we're done.
            if (not have_work) or not (limit > 0):
                break
            # More work, but check the time limit.
            now = time.ticks_us()
            delta = time.ticks_diff(now, start)
            if delta > limit:
                break
        return have_work

    def _err(self):
        try:
            if self._sock is not None:
                self._sock.close()
        except:
            pass
        self._sock = None
        self._addr = None
        self._rqst = b""
        self._ibuf = b""
        self._obuf = b""
        self._obufp = 0
        self._next = self._fetch
        return False
        
    def _fetch(self):
        have_work = False
        if self._restq:
            self._rqst = self._restq.pop(0)
            if self._debug > 1:
                print("Client: request:", self._rqst)
            self._obuf = b"GET " + self._rqst +  b" HTTP/1.0\r\nHost: " + self._my_addr + b"\r\nUser Agent: compat\r\nConnection: close\r\nAuthorization: Basic " + self._isy_auth + b"\r\n\r\n"
            self._obufp = 0
            self._next = self._open
            have_work = True
        return have_work

    def _open(self):
        self._addr = socket.getaddrinfo(self._isy_addr, self._isy_port)[0][-1]
        self._sock = socket.socket()
        self._sock.setblocking(False)
        self._next = self._connect
        return True

    def _connect(self):
        have_work = False
        try:
            self._sock.connect(self._addr)
            self._next = self._write
            have_work = True
        except OSError as e:
            if e.args[0] == 110:    # ETIMEDOUT   - will get this on first call
                pass
            elif e.args[0] == 115:  # EINPROGRESS - may get this on second
                pass
            elif e.args[0] == 114:  # EALREADY    - (already) connected
                self._next = self._write
            else:
                print("Client:", e)
                self._next = self._err
        return have_work

    def _write(self):
        have_work = False
        try:
            n = self._sock.send(self._obuf[self._obufp:])
            if n  > 0:
                if self._debug > 1:
                    print("Client: Writing", self._obuf[self._obufp:n])
                self._obufp += n
                if self._obufp >= len(self._obuf):
                    self._next = self._read
                have_work = True
            else:
                print("Client: Error: nothing written to client...")
        except OSError as e:
            if e.args[0] == 11:     # EAGAIN - operation would block
                pass
            elif e.args[0] == 110:  # ETIMEDOUT
                pass
            else:
                print("Client:", e)
                self._next = self._err
        return have_work

    def _read(self):
        have_work = False
        try:
            x = self._sock.recv(256)
            if len(x) > 0:
                self._ibuf += x
                if self._debug > 1:
                    print("Client: Reading", x)
                have_work = True
            else:
                if len(self._ibuf) > 0:
                    self._next = self._process
                    have_work = True
                else:
                    print("Client: No data to read yet...")
        except OSError as e:
            if e.args[0] == 11:     # EAGAIN - operation would block
                pass
            elif e.args[0] == 110:  # ETIMEDOUT
                pass
            else:
                print("Client:", e)
                self._next = self._err
        return have_work

    def _process(self):
        eol = self._ibuf.find(b"\r\n")
        tokens = self._ibuf[0:eol].split(b" ")
        if len(tokens) < 2:
            print("Client: Error: malformed response:", self._ibuf)
        else:
            if self._debug > 0:
                print("Client: {}: {}".format(int(tokens[1]), self._rqst))
        self._next = self._close
        return True

    def _close(self):
        try:
            self._sock.close()
        except:
            pass
        self._ibuf = b""
        self._obuf = b""
        self._rqst = b""
        self._obufp = 0
        self._next = self._fetch
        return True

# = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = # = = #
