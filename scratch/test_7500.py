import socket
import time

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10.0)
try:
    s.connect(('127.0.0.1', 7500))
    print("Connected to 127.0.0.1:7500 successfully!")
    start = time.time()
    while time.time() - start < 15.0:
        chunk = s.recv(1024)
        if chunk:
            print("Received from 7500:", chunk.decode('utf-8', errors='replace'))
            break
except socket.timeout:
    print("Timeout waiting for data from 7500")
except Exception as e:
    print("Error:", e)
finally:
    s.close()

