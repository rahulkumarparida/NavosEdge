import socket
import msgpack
import time

def test_mcu_rpc():
    u = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    u.settimeout(2.0)
    try:
        u.connect('/var/run/arduino-router.sock')
        print("Connected to /var/run/arduino-router.sock")
        
        req_env = [0, 100, "update_environment", [50.0, 10.0, 25.0, 40.0, 26.5, 60.0]]
        packed = msgpack.packb(req_env)
        print("Sending update_environment RPC...")
        u.sendall(packed)
        
        buf = bytearray()
        start = time.time()
        while time.time() - start < 3.0:
            try:
                chunk = u.recv(4096)
                if not chunk:
                    break
                buf.extend(chunk)
                try:
                    unpacked = msgpack.unpackb(buf)
                    print("Received FULL unpacked response:", unpacked)
                    break
                except msgpack.ExtraData as ed:
                    print("Extra data:", ed)
                    break
                except msgpack.FormatError:
                    pass
                except Exception:
                    pass
            except socket.timeout:
                break
        print(f"Total bytes received: {len(buf)}: {bytes(buf)!r}")
            
    except Exception as e:
        print("RPC Exception:", e)
    finally:
        u.close()

if __name__ == "__main__":
    test_mcu_rpc()
