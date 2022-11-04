"""
API Generator
"""
import json
import re

from errors import Forbidden
from logger import logger


class Api:
    def __init__(self):
        self.routes = {}

    def handle(self, event):
        # Extract event info
        record = event["Records"][0]
        request = record["cf"]["request"]
        method = request["method"]
        uri = request["uri"]

        # Find matching route
        route = None
        for pattern, methods in self.routes.items():
            if re.match(pattern, uri, re.IGNORECASE):
                route = methods.get(method)

        # Raise Forbidden
        if route is None:
            raise Forbidden

        # Execute request
        return route(request)

    def route(self, pattern, *methods):
        def inner(handler):
            def wrapper(request):
                return handler(request)

            # Set handler for pattern/methods
            self.routes[pattern] = {}
            for method in methods:
                self.routes[pattern][method] = wrapper

            return wrapper

        return inner

    def any(self, pattern):
        return self.route(pattern, "DELETE", "GET", "HEAD", "OPTIONS", "POST", "PUT")

    def post(self, pattern):
        return self.route(pattern, "POST")

    @classmethod
    def reject(cls, code, desc):
        return cls.respond(code, desc, {"ok": False})

    @staticmethod
    def respond(code, desc, body=None, **headers):
        """
        Send response instead of passing through to API Gateway

        :param int code: HTTP status code
        :param str desc: HTTP status text
        :param str body: HTTP response body
        """
        body = json.dumps(body) if body else ""
        if int(code) < 400:
            logger.info("RESPONSE [%d] %s", code, body or "-")
        else:
            logger.error("RESPONSE [%d] %s", code, body or "-")
        headers.setdefault("content-type", "application/json; charset=utf-8")
        headers = {k: [{"key": k, "value": v}] for k, v in headers.items()}
        response = {
            "status": str(code),
            "statusDescription": desc,
            "body": body,
            "headers": headers,
        }
        return response
