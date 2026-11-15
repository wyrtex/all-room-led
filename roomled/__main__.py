import argparse
import logging
import time
import webbrowser

from .app import App, serve
from .backends import FakeBackend, OpenRGBBackend
from .config import Config


def main():
    ap = argparse.ArgumentParser(prog="roomled")
    ap.add_argument("--demo", action="store_true", help="симулятор без железа")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")

    cfg = Config()
    backend = FakeBackend() if args.demo else OpenRGBBackend(exe_path=cfg["openrgb_path"])
    app = App(backend, cfg)
    app.start()
    serve(app, port=args.port)
    url = f"http://127.0.0.1:{args.port}"
    print(f"RoomLED запущен: {url}  (Ctrl+C для выхода)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        app.engine.stop()
        backend.close()


main()
