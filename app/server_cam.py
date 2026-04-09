from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pathlib import Path
from threading import Condition
import io

from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"

app = FastAPI()


class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        super().__init__()
        self.frame = None
        self.condition = Condition()

    def writable(self):
        return True

    def write(self, buf):
        with self.condition:
            self.frame = bytes(buf)
            self.condition.notify_all()
        return len(buf)


output = StreamingOutput()
picam2 = None


@app.on_event("startup")
def startup():
    global picam2

    picam2 = Picamera2()

    config = picam2.create_video_configuration(
        main={"size": (640, 480)}
    )
    picam2.configure(config)

    encoder = JpegEncoder(q=70)
    picam2.start_recording(encoder, FileOutput(output))

    print("[CAM] Picamera2 MJPEG server started")


@app.on_event("shutdown")
def shutdown():
    global picam2
    if picam2 is not None:
        try:
            picam2.stop_recording()
        except Exception:
            pass
        picam2.close()
        picam2 = None
        print("[CAM] Camera stopped")


def generate_mjpeg():
    while True:
        with output.condition:
            output.condition.wait()
            frame = output.frame

        if frame is None:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
            + frame + b"\r\n"
        )


@app.get("/")
def home():
    html_path = TEMPLATE_DIR / "index_cam.html"
    if not html_path.exists():
        return HTMLResponse("<h1>Missing index_cam.html</h1>")

    return HTMLResponse(
        html_path.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@app.get("/video")
def video():
    return StreamingResponse(
        generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.server_cam:app", host="0.0.0.0", port=8002, reload=False)
