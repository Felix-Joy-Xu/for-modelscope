"""Master launcher - runs all crawlers sequentially.

Usage:
    # Crawl direct-API companies only (fast, no browser needed):
    python run_all.py --direct

    # Crawl Boss Zhipin companies only (needs manual login):
    python run_all.py --boss

    # Crawl everything:
    python run_all.py --all
"""
import sys
import subprocess
from pathlib import Path

HERE = Path(__file__).parent


def run_script(rel_path):
    p = HERE / rel_path
    print(f"\n{'#'*60}")
    print(f"# Running: {p.name}")
    print(f"{'#'*60}")
    subprocess.run([sys.executable, str(p)], cwd=str(HERE))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nOptions: --direct  --boss  --all")
        return

    mode = sys.argv[1]

    if mode in ("--direct", "--all"):
        run_script("direct_api_crawlers.py")

    if mode in ("--boss", "--all"):
        print("\n[INFO] Boss Zhipin crawler requires manual login.")
        print("[INFO] A dialog will pop up - follow the instructions.")
        run_script("boss_zhipin_multi.py")

    print("\nAll crawlers finished.")


if __name__ == "__main__":
    main()
