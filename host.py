from pypresence import Presence
import socket
import json
import threading

clients = {}
lock = threading.Lock()

def get_presence(client_id):
    if client_id not in clients:
        rpc = Presence(client_id)
        try:
            rpc.connect()
            clients[client_id] = rpc
            print(f"[Host] Connected to Discord app ID: {client_id}")
        except Exception as e:
            print(f"[Host] Failed to connect to {client_id}: {e}")
            return None
    return clients[client_id]

def handle_client(conn, addr):
    print(f"[Host] Connection from {addr}")
    with conn:
        try:
            data = conn.recv(8192)
            payload = json.loads(data.decode())

            client_id = payload.get("client_id")
            if not client_id:
                # fallback to pid if client_id is missing
                client_id = str(payload.get("pid", "unknown_app"))
            
            print(f"[Host] Received presence update for client_id: {client_id}")

            # Extract the nested 'activity' dict if present
            activity = payload.get("activity", {})
            
            # Flatten timestamps from activity to root
            timestamps = activity.pop("timestamps", None)
            if timestamps:
                for key in ["start", "end"]:
                    if key in timestamps:
                        activity[key] = timestamps[key]

            # Flatten assets from activity to root
            assets = activity.pop("assets", None)
            if assets:
                for key in ["large_image", "large_text", "small_image", "small_text"]:
                    if key in assets:
                        activity[key] = assets[key]

            # Now merge any other root-level keys from payload (like pid)
            presence_data = {**activity}
            # Add any other keys you want from payload, except client_id and activity
            for k, v in payload.items():
                if k not in ["client_id", "activity"]:
                    presence_data[k] = v

            with lock:
                rpc = get_presence(client_id)
                if rpc:
                    rpc.update(**presence_data)
                    print(f"[Host] Updated presence for {client_id}: {presence_data.get('details', '')[:50]}")

        except Exception as e:
            print(f"[Host] Error handling client {addr}: {e}")

def start_server(host='0.0.0.0', port=1337):
    print(f"[Host] Listening on {host}:{port}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, port))
        s.listen(5)
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    try:
        start_server()
    except KeyboardInterrupt:
        print("\n[Host] Shutting down.")
        for rpc in clients.values():
            try:
                rpc.clear()
                rpc.close()
            except:
                pass