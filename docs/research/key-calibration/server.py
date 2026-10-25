"""Throwaway calibration server for ticket #12: serves the logging page and saves each run's events.

    python3 server.py            # then open http://<this Mac>:8765/ on any device on the network
"""

import json, os
from http.server import HTTPServer, SimpleHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS = os.path.join(HERE, "logs")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def do_POST(self):
        if self.path != "/log":
            return self.send_error(404)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        os.makedirs(LOGS, exist_ok=True)
        name = f"{body['board']}-{body['browser']}-{body['run']}.json"  # re-saves of a run overwrite
        with open(os.path.join(LOGS, name), "w") as f:
            json.dump(body, f, indent=1)
        print(f"saved {name}: {len(body['events'])} events")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"saved": name}).encode())


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8765), Handler).serve_forever()
