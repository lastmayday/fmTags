from tornado.wsgi import WSGIContainer
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from app import app

import sys

if __name__ == '__main__':
    http_server = HTTPServer(WSGIContainer(app))
    http_server.listen(int(sys.argv[1]))
    IOLoop.instance().start()
