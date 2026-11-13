"""OBS WebSocket v5 test client."""
import base64
import hashlib
import json
import os
import socket
import struct
import uuid


class Client:
    def __init__(self, port, password):
        self.socket = socket.create_connection(('127.0.0.1', port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        self.socket.sendall((f'GET / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        data = b''
        while b'\r\n\r\n' not in data:
            part = self.socket.recv(4096)
            if not part:
                raise ConnectionError('HTTP upgrade closed')
            data += part
        header, self.buffer = data.split(b'\r\n\r\n', 1)
        if b' 101 ' not in header:
            raise ConnectionError('Websocket upgrade refused')
        auth = self.receive()['d'].get('authentication')
        identify = {'rpcVersion': 1}
        if auth:
            secret = base64.b64encode(hashlib.sha256((password + auth['salt']).encode()).digest()).decode()
            identify['authentication'] = base64.b64encode(hashlib.sha256((secret + auth['challenge']).encode()).digest()).decode()
        self.send({'op': 1, 'd': identify})
        if self.receive()['op'] != 2:
            raise ConnectionError('Authentication failed')

    def send(self, message):
        data = json.dumps(message).encode()
        n = len(data)
        header = bytes([0x81, 0x80 | n]) if n < 126 else bytes([0x81, 0x80 | 126]) + struct.pack('>H', n)
        mask = os.urandom(4)
        self.socket.sendall(header + mask + bytes(v ^ mask[i % 4] for i, v in enumerate(data)))

    def read(self, n):
        while len(self.buffer) < n:
            data = self.socket.recv(65536)
            if not data:
                raise ConnectionError('Websocket closed')
            self.buffer += data
        data, self.buffer = self.buffer[:n], self.buffer[n:]
        return data

    def receive(self):
        while True:
            opcode, length = self.read(2)
            n = length & 127
            if n == 126:
                n = struct.unpack('>H', self.read(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', self.read(8))[0]
            data = self.read(n)
            if opcode & 15 == 1:
                return json.loads(data)
            if opcode & 15 == 8:
                raise ConnectionError('Websocket closed')

    def request(self, name, **data):
        rid = str(uuid.uuid4())
        self.send({'op': 6, 'd': {'requestType': name, 'requestId': rid, 'requestData': data}})
        while True:
            message = self.receive()
            if message['op'] == 7 and message['d'].get('requestId') == rid:
                response = message['d']
                if not response['requestStatus']['result']:
                    raise RuntimeError(f'{name}: {response["requestStatus"]}')
                return response.get('responseData', {})

    def close(self):
        self.socket.close()
