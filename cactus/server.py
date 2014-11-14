import os
import sys
import logging
import threading
import mime

logger = logging.getLogger(__name__)

import tornado.httpserver
import tornado.websocket
import tornado.ioloop
import tornado.web

TEMPLATES = {}
FORCED_HTML_PATHS = set()

class WebSocketHandler(tornado.websocket.WebSocketHandler):
    
    def open(self):
        if self not in self.application._socketHandlers:
            self.application._socketHandlers.append(self)

    def on_close(self):
        if self in self.application._socketHandlers:
            self.application._socketHandlers.remove(self)

    def on_message(self, msg):
        pass

class StaticHandler(tornado.web.StaticFileHandler):
    
    def get(self, *args, **kwargs):

        super(StaticHandler, self).get(*args, **kwargs)

        if self.get_content_type() == "text/html":
            self.finish(TEMPLATES["script"])

    # Always be not caching
    def should_return_304(self):
        return False

    def get_content_type(self):
        global FORCED_HTML_PATHS
        if self.path in FORCED_HTML_PATHS:
            return "text/html"
        try:
            return mime.guess(self.absolute_path)
        except AttributeError:
            raise AttributeError('StaticHandler for {} does not have absolute_path attribute'.format(self.path))

    def write_error(self, status_code, **kwargs):

        if status_code == 404:
            return self.render("error.html")

        return super(StaticHandler, self).write_error(status_code, **kwargs)

    def log_request(self, handler):
        pass

class StaticSingleFileHandler(tornado.web.RequestHandler):

    def get(self):
        self.set_header("Content-Type", mime.guess("file.js"))
        self.finish(TEMPLATES["js"])

class WebServer(object):

    def __init__(self, path, port=8080):
        self.path = path.decode("utf-8")
        self.port = port

        handlers = [
            (r'/_cactus/ws', WebSocketHandler),
            (r'/_cactus/cactus.js', StaticSingleFileHandler),
        ]

        global FORCED_HTML_PATHS
        # coerce top level page files to be served as html
        for top_level_page_filename in os.listdir(path):
            if '.' not in top_level_page_filename and os.path.isfile(os.path.join(path, top_level_page_filename)):
                FORCED_HTML_PATHS.add(top_level_page_filename)

        handlers.append((r'/(.*)', StaticHandler, {'path': self.path, "default_filename": "index.html"}))
        self.application = tornado.web.Application(handlers, template_path=self.path)
        self.application.log_request = lambda x: self._log_request(x)

    def _log_request(self, handler):

        if not isinstance(handler, StaticHandler):
            return

        if handler.get_status() < 400:
            log_method = logging.info
        elif handler.get_status() < 500:
            log_method = logging.warning
        else:
            log_method = logging.error

        log_method("%d %s %s", handler.get_status(), handler.request.method, handler.request.uri)


    def start(self):

        self.application._socketHandlers = []

        self._server = tornado.httpserver.HTTPServer(self.application)
        self._server.listen(self.port)

        tornado.ioloop.IOLoop.instance().start()

    def stop(self):
        pass

    def publish(self, message):
        for ws in self.application._socketHandlers:
            ws.write_message(message)

    def reloadPage(self):
        self.publish("reloadPage")

    def reloadCSS(self):
        self.publish("reloadCSS")

TEMPLATES["script"] = """

<!-- Automatically inserted by Cactus. Needed for auto refresh. This will be gone when you deploy -->
<script src="/_cactus/cactus.js"></script>
"""

TEMPLATES["js"] = """
(function() {

function reloadPage() {
    window.location.reload()
}

function reloadCSS() {
    function updateQueryStringParameter(uri, key, value) {

        var re = new RegExp("([?|&])" + key + "=.*?(&|$)", "i");
        separator = uri.indexOf("?") !== -1 ? "&" : "?";

        if (uri.match(re)) {
            return uri.replace(re, "$1" + separator + key + "=" + value + "$2");
        } else {
            return uri + separator + key + "=" + value;
        };
    };

    var links = document.getElementsByTagName("link");

    for (var i = 0; i < links.length;i++) {

        var link = links[i];

        if (link.rel === "stylesheet") {

            // Don"t reload external urls, they likely did not change
            if (
                link.href.indexOf("127.0.0.1") == -1 && 
                link.href.indexOf("localhost") == -1 &&
                link.href.indexOf("0.0.0.0") == -1 &&
                link.href.indexOf(window.location.host) == -1
                ) {
                continue;
            }

            var updatedLink = updateQueryStringParameter(link.href, "cactus.reload", new Date().getTime());

            if (updatedLink.indexOf("?") == -1) {
                updatedLink = updatedLink.replace("&", "?");
            };

            link.href = updatedLink;
        };
    };
};

function startSocket() {

    var MessageActions = {
        reloadPage: reloadPage,
        reloadCSS: reloadCSS
    };

    var socketUrl = "ws://" + window.location.host + "/_cactus/ws"
    var socket = new WebSocket(socketUrl);

    socket.onmessage = function(e) {
        var key = e.data;

        if (MessageActions.hasOwnProperty(key)) {
            MessageActions[key]()
        };
    };
};

startSocket();

})()
"""


