"""
ChronosMatch Master Live Demo Launcher
======================================
One-click runner for internship presentations and viva demonstrations:
1. Boots FastAPI ChronosMatch engine with SQLite persistence
2. Waits for health checks to pass
3. Opens the real-time web dashboard in the system default browser
4. Streams simulated live orders, market depth, and executions
5. Gracefully handles shutdown on Ctrl+C

Usage:
    python run_demo.py
"""
import os
import sys
import time
import subprocess
import webbrowser
import urllib.request
import signal

BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
HEALTH_URL = "http://127.0.0.1:8000/health"
DASHBOARD_URL = "http://127.0.0.1:8000/dashboard"


def wait_for_backend(timeout: int = 15) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main():
    print("=" * 60)
    print("  CHRONOSMATCH: ZERO-COPY HIGH-FREQUENCY MATCHING ENGINE")
    print("  Interactive Internship Demonstration Environment")
    print("=" * 60)

    # 1. Start backend process
    print("\n[1/4] Starting FastAPI High-Performance Matching Server...")
    server_cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"]
    server_proc = subprocess.Popen(
        server_cmd,
        cwd=BACKEND_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    try:
        # 2. Wait for healthy response
        print("[2/4] Waiting for engine initialization & SQLite persistence...")
        if not wait_for_backend():
            print("\n[ERROR] Server failed to start within timeout.")
            server_proc.kill()
            sys.exit(1)
        print("      -> Engine initialized! REST APIs & in-memory book ready.")

        # 3. Open browser dashboard
        print(f"[3/4] Launching Dashboard in browser: {DASHBOARD_URL}")
        try:
            webbrowser.open(DASHBOARD_URL)
        except Exception as e:
            print(f"      (Could not auto-open browser: {e}. Please open manually.)")

        # 4. Start live market simulator in foreground
        print("\n[4/4] Starting Live Simulated Market Feed (AAPL)...")
        print("      Dashboard URL : http://127.0.0.1:8000/dashboard")
        print("      Swagger Docs  : http://127.0.0.1:8000/docs")
        print("      Press Ctrl+C at any time to shut down the server and demo.\n")

        sim_cmd = [sys.executable, os.path.join(BACKEND_DIR, "simulate_market.py"), "--symbol", "AAPL", "--interval", "0.5"]
        sim_proc = subprocess.Popen(sim_cmd, cwd=BACKEND_DIR)
        sim_proc.wait()

    except KeyboardInterrupt:
        print("\n\nShutting down ChronosMatch demo services...")
    finally:
        try:
            server_proc.terminate()
            server_proc.wait(timeout=2)
        except Exception:
            server_proc.kill()
        print("Demo services cleanly stopped. Goodbye!")


if __name__ == "__main__":
    main()
