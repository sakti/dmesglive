import tornado.options
import tornado.ioloop
import tornado.web
from tornado import websocket
import logging
import sys
from subprocess import PIPE, Popen
from threading import Thread
from Queue import Queue, Empty


logger = logging.getLogger(__name__)
GLOBALS = {
    "sockets": [],
}
ON_POSIX = "posix" in sys.builtin_module_names


def enqueue_output(out, queue):
    for line in iter(out.readline, ''):
        queue.put(line)
    out.close()

proc = Popen(["tail", "-f", "/var/log/syslog"], stdout=PIPE,
                bufsize=1, close_fds=ON_POSIX)
queue = Queue()
thread = Thread(target=enqueue_output, args=(proc.stdout, queue))
thread.daemon = True
thread.start()


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("""
        <!DOCTYPE html>
        <html>
            <head>
                <title>dmesglive</title>
                <script>
                    document.addEventListener("DOMContentLoaded", function() {
                        var WS = window["MozWebSocket"] ? MozWebSocket : WebSocket;
                        var ws_url = "ws://" + window.location.host + "/websocket";
                        var ws = new WS(ws_url);
                        var output = document.getElementById("output");
                        ws.onmessage = function(event) {
                            output.innerText += event.data;

                            // auto scroll window
                            window.scroll(0, document.height);
                        };
                    });
                </script>
                <style>
                    body {
                        background:black;
                        color:lightgreen;
                    }
                </style>
            </head>
            <body>
                <pre id="output"></pre>
            </body>
        </html>
        """)


class ClientSocket(websocket.WebSocketHandler):
    def open(self):
        GLOBALS['sockets'].append(self)
        logger.info("Websocket opened")

    def close(self):
        logger.info("Websocket closed")
        GLOBALS['sockets'].remove(self)


def push_to_client():
    # do websockets filtering
    GLOBALS['sockets'] = filter(lambda x: x.ws_connection != None,
                                GLOBALS['sockets'])
    try:
        message = queue.get_nowait()
    except Empty:
        return

    logger.info("push into %s client(s)" % len(GLOBALS['sockets']))

    for socket in GLOBALS['sockets']:
        socket.write_message(message)

application = tornado.web.Application([
    (r"/", MainHandler),
    (r"/websocket", ClientSocket),
])

if __name__ == "__main__":
    tornado.options.parse_command_line()

    main_loop = tornado.ioloop.IOLoop.instance()

    # setup scheduler for push log content to web client
    scheduler = tornado.ioloop.PeriodicCallback(push_to_client,
                                                1 * 500, main_loop)
    application.listen(8888)
    scheduler.start()
    try:
        main_loop.start()
    except(KeyboardInterrupt, SystemExit):
        logger.info("Shutting down")
