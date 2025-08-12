import socket
import json
import win32pipe, win32file, threading, struct

HOST = "172.16.17.1"
PORT = 1337
PIPES = [f"\\\\.\\pipe\\discord-ipc-{i}" for i in range(10)]

def read_frame(pipe):
    try:
        header = win32file.ReadFile(pipe, 8)[1]
        if len(header) < 8:
            return None, None
        op, length = struct.unpack("<II", header)
        body = win32file.ReadFile(pipe, length)[1]
        return op, json.loads(body.decode("utf-8"))
    except Exception as e:
        print(f"[VM] Error reading frame: {e}")
        return None, None

def send_frame(pipe, op, payload):
    try:
        encoded = json.dumps(payload).encode('utf-8')
        header = struct.pack("<II", op, len(encoded))
        win32file.WriteFile(pipe, header + encoded)
    except Exception as e:
        print(f"[VM] Error sending frame: {e}")

def forward_to_host(payload):
    try:
        with socket.create_connection((HOST, PORT)) as s:
            print(f"[VM] Connected to host {HOST}:{PORT}")
            s.sendall(json.dumps(payload).encode("utf-8"))
            print(f"[VM] Forwarded presence update for client_id={payload.get('client_id', 'unknown')}")
    except Exception as e:
        print(f"[VM] Failed to send payload: {e}")

def proxy_pipe(path):
    print(f"[VM] Listening on pipe {path}")
    try:
        pipe = win32pipe.CreateNamedPipe(
            path,
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_WAIT,
            10, 4096, 4096,
            0,
            None
        )
        while True:
            win32pipe.ConnectNamedPipe(pipe, None)
            print(f"[VM] Client connected on {path}")

            client_id = None  # reset for each connection

            # Read handshake message
            op, payload = read_frame(pipe)
            if not payload:
                win32pipe.DisconnectNamedPipe(pipe)
                continue

            print(f"[VM] Received handshake:")
            print(json.dumps(payload, indent=2))

            # Store client_id from handshake
            client_id = payload.get("client_id")

            # Send minimal READY event
            ready_payload = {
                "cmd": "DISPATCH",
                "evt": "READY",
                "data": {
                    "v": 1,
                    "config": {},
                }
            }
            send_frame(pipe, 1, ready_payload)

            while True:
                op, payload = read_frame(pipe)
                if not payload:
                    break

                print(f"[VM] Received message:")
                print(json.dumps(payload, indent=2))

                if payload.get("cmd") == "SET_ACTIVITY":
                    args = payload.get("args", {})

                    # Inject client_id if missing
                    if not client_id:
                        client_id = args.get("client_id") or args.get("application_id")
                    if client_id:
                        args["client_id"] = client_id
                    else:
                        print("[VM] Warning: no client_id available for this connection")

                    # Link client_id into assets for clarity (optional but recommended)
                    activity = args.get("activity", {})
                    if "assets" in activity:
                        activity["assets"]["client_id"] = client_id
                    else:
                        activity["assets"] = {"client_id": client_id}
                    args["activity"] = activity

                    forward_to_host(args)

            win32pipe.DisconnectNamedPipe(pipe)

    except Exception as e:
        print(f"[VM] Pipe error on {path}: {e}")


if __name__ == "__main__":
    for path in PIPES:
        threading.Thread(target=proxy_pipe, args=(path,), daemon=True).start()
    print("[VM] Discord RPC Proxy running...")
    threading.Event().wait()