#!/usr/bin/env python3
"""ProjectToMarkdown – local web UI entry point.

Starts a loopback HTTP server (see ``server.py``) and opens the app in your
default browser.  The UI is plain HTML/JS served from ``web/``, so the app
runs anywhere Python runs – no GUI toolkit required.

Usage:
    python main.py               # random free port, opens the browser
    python main.py --port 8765   # fixed port
    python main.py --no-browser  # just print the URL
"""

import argparse
import threading
import webbrowser

from server import create_server

APP_VERSION = "1.0.0"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="project_to_markdown",
        description="Bridge your local projects to free chat LLMs – "
                    "no API keys needed.",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=0,
        help="port to serve on (0 = a random free port, default)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help=(
            "address to bind to (default: 127.0.0.1, loopback only). "
            "Use 0.0.0.0 to expose the server to a Docker container or "
            "the local network."
        ),
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="do not open the web browser automatically",
    )
    args = parser.parse_args()

    server = create_server(host=args.host, port=args.port)
    host, port = server.server_address[0], server.server_address[1]
    url = f"http://{host}:{port}/"

    print(f"ProjectToMarkdown v{APP_VERSION}", flush=True)
    print(f"Serving on {url}  (press Ctrl+C to quit)", flush=True)

    if not args.no_browser:
        # Give the server a moment before the browser fires its first request.
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
