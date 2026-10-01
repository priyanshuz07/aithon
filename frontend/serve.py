"""Serve the frontend from its own directory, independent of the shell CWD."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FRONTEND_ROOT = Path(__file__).resolve().parent


def create_server(host: str = "127.0.0.1", port: int = 5500) -> ThreadingHTTPServer:
    handler = partial(SimpleHTTPRequestHandler, directory=str(FRONTEND_ROOT))
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5500)
    arguments = parser.parse_args()
    server = create_server(arguments.host, arguments.port)
    print(f"Serving {FRONTEND_ROOT} at http://{arguments.host}:{arguments.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
