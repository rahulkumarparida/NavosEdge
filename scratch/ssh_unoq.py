import paramiko
import sys

def run_ssh_command(cmd):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect('10.81.210.140', username='arduino', password='garuda@q', timeout=10)
        stdin, stdout, stderr = client.exec_command(cmd)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        print(f"=== CMD: {cmd} ===")
        if out:
            print("[STDOUT]")
            print(out)
        if err:
            print("[STDERR]")
            print(err)
        client.close()
    except Exception as e:
        print(f"SSH Exception: {e}", file=sys.stderr)

if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "uname -a"
    run_ssh_command(command)

