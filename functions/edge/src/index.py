"""
Lambda Entrypoint
"""
import json

import env

env.export()  # Export SecretsManager JSON to environment

from api import Api
from events import CloudFrontEvent, Callback, Event, Menu, OAuth, Slash
from errors import Forbidden, NotFound
from logger import logger
from slackbot import Slackbot

api = Api()
bot = Slackbot()


# Sign request & pass through to API Gateway
@api.any(r"^/health")
def any_health(request):
    event = CloudFrontEvent(request)
    return bot.resolve(event)


# Redirect to Slack install URL
@api.any(r"^/install")
def any_install(_):
    location = bot.oauth.install_uri
    return api.respond(302, "FOUND", location=location)


# Complete OAuth workflow, publish event, and redirect to OAuth success URI
@api.any(r"^/oauth")
def any_oauth(request):
    event = OAuth(request)
    location = bot.install(event)
    return api.respond(302, "FOUND", location=location)


# Verify origin, publish to EventBridge, then sign & pass through to API Gateway
@api.post(r"^/callbacks$")
def post_callbacks(request):
    event = Callback(request)
    bot.verify(event)
    bot.publish(event)
    return bot.resolve(event)


# Verify origin, publish to EventBridge, then respond 200 OK
@api.post(r"^/events$")
def post_events(request):
    event = Event(request)
    bot.verify(event)
    bot.publish(event)

    # First-time URL verification for events
    body = None
    payload = event.get_payload()
    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        body = {"challenge": challenge}

    return api.respond(200, "OK", body)


# Verify origin, publish to EventBridge, then sign & pass through to API Gateway
@api.post(r"^/menus$")
def post_menus(request):
    event = Menu(request)
    bot.verify(event)
    bot.publish(event)
    return bot.resolve(event)


# Verify origin, publish to EventBridge, then sign & pass through to API Gateway
@api.post(r"^/slash\.[a-z_-]+$")
def post_slash(request):
    event = Slash(request)
    bot.verify(event)
    bot.publish(event)
    return bot.resolve(event)


@logger.bind
def handler(event, *_):
    """
    Lambda@Edge handler for CloudFront
    """
    try:
        return api.handle(event)
    except Forbidden as err:
        return api.reject(403, "FORBIDDEN")
    except Exception as err:
        logger.error("%s", err)
        return api.reject(500, "INTERNAL SERVER ERROR")
