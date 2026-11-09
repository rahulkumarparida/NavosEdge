import paramiko
import sys

DIAG_SCRIPT = """
import socket
import sys
import time

print("=== 1. Testing TCP 127.0.0.1:7500 (Monitor Proxy) ===")
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(4.0)
    s.connect(('127.0.0.1', 7500))
    print("[TCP 7500] Connected successfully!")
    data = s.recv(1024)
    print(f"[TCP 7500] Received {len(data)} bytes: {data!r}")
    s.close()
except socket.timeout:
    print("[TCP 7500] Timeout: Connected, but 0 bytes received in 4.0s")
except Exception as e:
    print(f"[TCP 7500] Error: {e}")

print("\\n=== 2. Testing UNIX /var/run/arduino-router.sock (RPC Socket) ===")
try:
    u = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    u.settimeout(4.0)
    u.connect('/var/run/arduino-router.sock')
    print("[UNIX SOCK] Connected successfully!")
    
    # Try calling $/version method via msgpack-rpc
    # msgpack for [0, 1, "$/version", []]
    # 0x94 (fixarray 4), 0x00 (req=0), 0x01 (msgid=1), 0xa9 (fixstr 9), '$/version', 0x90 (fixarray 0)
    req = b'\\x94\\x00\\x01\\xa9$/version\\x90'
    u.sendall(req)
    resp = u.recv(1024)
    print(f"[UNIX SOCK] Sent $/version, received {len(resp)} bytes: {resp!r}")
    u.close()
except Exception as e:
    print(f"[UNIX SOCK] Error: {e}")
"""

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect('10.81.210.140', username='arduino', password='garuda@q', timeout=10)
    
    # Upload script
    sftp = client.open_sftp()
    with sftp.file('/tmp/diag_unoq.py', 'w') as f:
        f.write(DIAG_SCRIPT)
    sftp.close()
    
    # Run script
    stdin, stdout, stderr = client.exec_command('python3 /tmp/diag_unoq.py')
    print(stdout.read().decode('utf-8', errors='replace'))
    err = stderr.read().decode('utf-8', errors='replace')
    if err:
        print("[STDERR]", err)
        
    client.close()

if __name__ == "__main__":
    main()

