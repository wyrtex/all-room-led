import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from roomled.app import App, serve
from roomled.backends import FakeBackend
from roomled.config import Config
from roomled.effects import EFFECTS, make_effect, hex_to_rgb
from roomled.engine import apply_order


class Core(unittest.TestCase):
    def make_app(self):
        cfg = Config(Path(tempfile.mkdtemp()) / "c.json")
        app = App(FakeBackend(), cfg)
        app.engine.rescan()
        return app

    def test_all_effects_render_valid_frames(self):
        for name in EFFECTS:
            e = make_effect(name, 17, ["#ff0000", "#00ff00"], 1.0)
            for t in (0.0, 0.5, 3.3, 10.0):
                f = e.render(t)
                self.assertEqual(len(f), 17, name)
                for c in f:
                    self.assertTrue(all(0 <= v <= 255 for v in c), (name, c))

    def test_twinkle_only_palette_hues(self):
        e = make_effect("twinkle", 99, ["#ff0000", "#00ff00"], 1.0)
        lit = 0
        for i in range(200):
            for r, g, b in e.render(i * 0.05):
                self.assertEqual(b, 0)
                lit += (r > 0) + (g > 0)
        self.assertGreater(lit, 100)

    def test_color_order_fixes_red_shown_as_green(self):
        # железо ждёт GRB: чтобы получить красный, красный байт идёт вторым
        self.assertEqual(apply_order((255, 0, 0), "GRB"), (0, 255, 0))
        self.assertEqual(apply_order((1, 2, 3), "RGB"), (1, 2, 3))

    def test_new_year_scene_writes_frames(self):
        app = self.make_app()
        app.run_scene("Новый год")
        app.engine.tick(5.0)
        self.assertEqual(app.active_scene, "Новый год")
        board = app.engine.backend.frames["ASRock B650 Steel Legend WiFi"]
        self.assertEqual(len(board), 49)
        self.assertTrue(all(c in [(255, 0, 0), (0, 255, 0)] for c in board[:48]))

    def test_order_applied_to_output(self):
        app = self.make_app()
        key = "ASRock B650 Steel Legend WiFi::Addressable Header 1"
        app.set_order(key, "GRB")
        app.apply([key], "static", ["#ff0000"], 1)
        app.engine.tick(0.0)
        self.assertEqual(app.engine.backend.frames["ASRock B650 Steel Legend WiFi"][0], (0, 255, 0))

    def test_save_scene_roundtrip_and_groups(self):
        app = self.make_app()
        app.apply(["@keyboards"], "rainbow", ["#ff0000"], 1)
        app.save_scene("моя")
        sc = app.cfg["scenes"]["моя"]
        self.assertEqual(sc["assignments"][0]["effect"], "rainbow")
        self.assertEqual(len(sc["assignments"][0]["targets"]), 2)
        app.save_group("кб", sc["assignments"][0]["targets"])
        app.apply(["кб"], "off", ["#000000"], 1)

    def test_http_api(self):
        app = self.make_app()
        srv = serve(app, port=0)
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        st = json.load(urllib.request.urlopen(base + "/api/state"))
        self.assertEqual(len(st["devices"]), 3)
        req = urllib.request.Request(base + "/api/scene", json.dumps({"name": "Радуга"}).encode(), method="POST")
        self.assertTrue(json.load(urllib.request.urlopen(req))["ok"])
        self.assertIn(b"RoomLED", urllib.request.urlopen(base + "/").read())
        srv.shutdown()


if __name__ == "__main__":
    unittest.main()
