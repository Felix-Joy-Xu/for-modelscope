import subprocess
import sys
from pathlib import Path

BASE = Path(r"D:\国际比较政治经济学\01-爬虫程序")
log = open(BASE / "crawl_comments.log", "a", encoding="utf-8")

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

proc = subprocess.Popen(
    [r"D:\python\python.exe", "-u", str(BASE / "crawl_ms_comments_api.py")],
    cwd=str(BASE),
    stdout=log,
    stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL,
    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
    close_fds=True,
)
print(f"launched PID={proc.pid}")
