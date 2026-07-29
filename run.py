#!/usr/bin/env python3
"""Breachwright Desktop Application

Starts the backend and opens a native application window.
No browser, no Docker, no exposed ports.

Usage:
    breachwright              # Launch the app
    breachwright --setup      # Create admin account
    breachwright --headless   # API server only (no window)
"""
import argparse
import logging
import os
import sys
import threading
import time

# On Windows GUI exe (console=False), stdout/stderr are None — redirect to devnull
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

# Determine base directory (frozen vs dev)
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    APP_ROOT = sys._MEIPASS
else:
    APP_ROOT = os.path.dirname(os.path.abspath(__file__))

BACKEND_DIR = os.path.join(APP_ROOT, "backend")
if os.path.isdir(BACKEND_DIR):
    os.chdir(BACKEND_DIR)
    if BACKEND_DIR not in sys.path:
        sys.path.insert(0, BACKEND_DIR)
else:
    # Fallback: backend might be at cwd already (install.sh layout)
    if os.path.isdir("backend"):
        os.chdir("backend")
        sys.path.insert(0, os.getcwd())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("breachwright")


def start_server(host, port):
    import uvicorn
    if getattr(sys, 'frozen', False):
        # Frozen: import app object directly (string import unreliable)
        from app.main import app as application
        uvicorn.run(
            application,
            host=host,
            port=port,
            log_level="warning",
        )
    else:
        uvicorn.run(
            "app.main:app",
            host=host,
            port=port,
            log_level="warning",
            reload=False,
        )


def wait_for_server(host, port, timeout=20):
    import urllib.request
    url = f"http://{host}:{port}/api/health"
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def run_setup():
    from app.auth.setup import setup
    setup()


def launch_window(host, port):
    try:
        import webview
    except ImportError:
        logger.warning("pywebview not available, falling back to browser")
        import webbrowser
        webbrowser.open(f"http://{host}:{port}")
        print(f"\n  Opened in browser: http://{host}:{port}")
        print("  Press Ctrl+C to stop the server.\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return

    window = webview.create_window(
        title="Breachwright // Advent Cybersecurity",
        url=f"http://{host}:{port}",
        width=1400,
        height=900,
        min_size=(1024, 680),
        resizable=True,
        background_color="#0a0a0f",
        text_select=True,
    )

    def on_closing():
        os._exit(0)

    window.events.closing += on_closing
    # Force EdgeChromium on Windows (avoid pythonnet/WinForms fallback)
    import platform
    gui_backend = 'edgechromium' if platform.system() == 'Windows' else None
    webview.start(debug=False, private_mode=True, gui=gui_backend)


def main():
    parser = argparse.ArgumentParser(description="Breachwright")
    parser.add_argument("--setup", action="store_true", help="Create admin account")
    parser.add_argument("--headless", action="store_true", help="Run server only, no GUI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=13370)
    args = parser.parse_args()

    if args.setup:
        run_setup()
        return

    print()
    print("  +----------------------------------------------+")
    print("  |              BREACHWRIGHT v2.0.0             |")
    print("  |         An Advent Cybersecurity Product       |")
    print("  +----------------------------------------------+")
    print()

    if args.headless:
        print(f"  Server: http://{args.host}:{args.port}")
        print(f"  Docs:   http://{args.host}:{args.port}/api/docs")
        print()
        start_server(args.host, args.port)
    else:
        server = threading.Thread(
            target=start_server,
            args=(args.host, args.port),
            daemon=True,
        )
        server.start()

        print(f"  Starting server...")

        if wait_for_server(args.host, args.port):
            print(f"  Opening application window...")
            print()
            launch_window(args.host, args.port)
        else:
            print("  ERROR: Server failed to start. Run with --headless to see logs.")
            sys.exit(1)


if __name__ == "__main__":
    main()
