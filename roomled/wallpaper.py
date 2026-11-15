"""Смена обоев в Wallpaper Engine через командную строку."""
from __future__ import annotations

import logging
import os
import subprocess

log = logging.getLogger("roomled.wallpaper")


def set_wallpaper(exe: str, project_json: str) -> bool:
    """project_json — путь к project.json нужных обоев (из папки Steam Workshop)."""
    if not project_json:
        return False
    if not exe or not os.path.exists(exe):
        log.warning("wallpaper64.exe не найден: %s", exe)
        return False
    subprocess.Popen([exe, "-control", "openWallpaper", "-file", project_json])
    return True
