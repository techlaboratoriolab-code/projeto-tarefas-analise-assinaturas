from http.server import BaseHTTPRequestHandler
import json


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        response = json.dumps({
            'status': 'ok',
            'service': 'LAB TISS Processor',
            'version': '1.0.0'
        }, ensure_ascii=False).encode('utf-8')

        self.wfile.write(response)
