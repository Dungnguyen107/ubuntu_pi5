from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pathlib import Path

import asyncio
import json
import threading
import time
import subprocess
import re

# ─── Config ──────────────────────────────────────────────────
UART_PORT      = "/dev/ttyUSB0"
UART_BAUDRATE  = "115200"
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
UART_BINARY    = BASE_DIR /"bin"/ "uart_reader"

app = FastAPI()

clients: set[WebSocket] = set()
loop: asyncio.AbstractEventLoop | None = None

# ─── Broadcast tới tất cả WebSocket client ───────────────────
async def broadcast(obj: dict):
    text = json.dumps(obj, ensure_ascii=False)
    dead = []
    for ws in clients:
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)

async def send_json(ws: WebSocket, obj: dict):
    await ws.send_text(json.dumps(obj, ensure_ascii=False))

# ─── Parse dòng output từ uart_reader C ──────────────────────
# Các format uart_reader in ra:
#   [10:23:41] RPM   :   3200 vòng/phút
#   [10:23:41] TEMP  :     85 °C
#   [10:23:41] [RAW] ...
def parse_uart_line(line: str) -> dict | None:
    """
    Trả về dict telemetry hoặc None nếu không parse được.
    """
    line = line.strip()
    if not line:
        return None

    # RPM: "[HH:MM:SS] RPM   :   3200 vòng/phút"
    m = re.search(r'RPM\s*:\s*(\d+)', line)
    if m:
        return {
            "type": "telemetry",
            "field": "rpm",
            "value": int(m.group(1)),
            "unit": "RPM",
            "raw": line,
            "ts": time.time(),
        }

    # TEMP: "[HH:MM:SS] TEMP  :     85 °C"
    m = re.search(r'TEMP\s*:\s*(\d+)', line)
    if m:
        return {
            "type": "telemetry",
            "field": "temp",
            "value": int(m.group(1)),
            "unit": "°C",
            "raw": line,
            "ts": time.time(),
        }

    # Snapshot tổng hợp: "──── RPM=3200 | Temp=85°C ────"
    m = re.search(r'RPM=(\d+)\s*\|\s*Temp=(\d+)', line)
    if m:
        return {
            "type": "snapshot",
            "rpm": int(m.group(1)),
            "temp": int(m.group(2)),
            "raw": line,
            "ts": time.time(),
        }

    # Dòng khác (INFO, OK, RAW...) → vẫn gửi để debug
    return {
        "type": "log",
        "raw": line,
        "ts": time.time(),
    }

# ─── Thread đọc stdout từ tiến trình C ───────────────────────
def uart_reader_thread():
    global loop

    if not UART_BINARY.exists():
        print(f"[ERROR] Không tìm thấy binary: {UART_BINARY}")
        print( "Build bằng: gcc uart_reader.c -o uart_reader")
        return

    cmd = [str(UART_BINARY), UART_PORT, UART_BAUDRATE]
    print(f"[INFO] Khởi chạy subprocess: {' '.join(cmd)}")

    while True:  # Tự restart nếu subprocess crash
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,   # Gộp stderr vào stdout
                text=True,
                bufsize=1,                  # Line-buffered
            )

            print(f"[INFO] uart_reader PID={proc.pid}")

            for line in proc.stdout:        # Block đọc từng dòng
                if loop is None:
                    continue

                msg = parse_uart_line(line)
                if msg is None:
                    continue

                print(f"[UART] {line.strip()}")

                asyncio.run_coroutine_threadsafe(
                    broadcast(msg),
                    loop,
                )

            proc.wait()
            print(f"[WARN] uart_reader thoát (code={proc.returncode}), restart sau 2s...")

        except Exception as e:
            print(f"[ERROR] subprocess lỗi: {e}")

        time.sleep(2)   # Chờ trước khi restart

# ─── FastAPI lifecycle ────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    global loop
    loop = asyncio.get_running_loop()
    threading.Thread(target=uart_reader_thread, daemon=True).start()

# ─── HTTP route ───────────────────────────────────────────────
@app.get("/")
def home():
    html_path = TEMPLATES_DIR / "index_ws.html"
    if not html_path.exists():
        return HTMLResponse("<h1>Missing index_ws.html</h1>")
    return HTMLResponse(
        html_path.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store"},
    )

# ─── WebSocket endpoint ───────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    print(f"[WS] Client kết nối ({len(clients)} total)")

    await send_json(ws, {
        "type": "hello",
        "text": "connected",
        "ts": time.time(),
    })

    try:
        while True:
            raw = await ws.receive_text()
            print(f"[WEB→] {raw}")
    except WebSocketDisconnect:
        print("[WS] Client ngắt kết nối")
    finally:
        clients.discard(ws)

# ─── Entry point ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.server_ws_log:app", host="0.0.0.0", port=8001, reload=False)
