"""
Slackbot client
"""
import hmac
import json
import os
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from time import time

from aws import EventBus, SigV4Signer
from errors import Forbidden
from logger import logger


class Slackbot:
    def __init__(self, event_bus=None, oauth=None, signer=None, sigv4signer=None):
        self.event_bus = event_bus or EventBus()
        self.oauth = oauth or OAuth()
        self.signer = signer or Signer()
        self.sigv4signer = sigv4signer or SigV4Signer()

    def install(self, event):
        query = event.get_query()

        # Handle explicit denials
        err = query.get("error")
        if err:
            error_url = self.oauth.error_uri.format(error=err)
            return error_url

        # Check state
        state = query.get("state")
        if not self.oauth.verify_state(state):
            logger.error("Invalid state parameter")
            error_url = self.oauth.error_uri.format(error="Invalid state parameter")
            return error_url

        # Set up OAuth request
        url = "https://slack.com/api/oauth.v2.access"
        headers = {"content-type": "application/x-www-form-urlencoded"}
        payload = {
            "code": query.get("code"),
            "client_id": self.oauth.client_id,
            "client_secret": self.oauth.client_secret,
            "redirect_uri": self.oauth.redirect_uri,
        }
        safe_payload = {k: v for k, v in payload.items() if v is not None}
        data = urlencode(safe_payload).encode()

        # Execute request to complete OAuth workflow
        logger.info("POST %s %s", url, json.dumps(safe_payload))
        req = Request(url, data, headers, method="POST")
        res = urlopen(req)

        # Parse response or return error
        try:
            resdata = res.read().decode()
            result = json.loads(resdata)
        except Exception as err:
            error = "Could not read OAuth response"
            error_url = self.oauth.error_uri.format(error=error)
            return error_url

        # Log errors & return
        if not result.get("ok"):
            logger.error("OAUTH RESPONSE [%d] %s", res.status, resdata)
            error_url = self.oauth.error_uri.format(**result)
            return error_url

        # Publish event
        entry = {
            "DetailType": "oauth",
            "Detail": json.dumps({"discriminator": "install", "payload": result}),
        }
        self.event_bus.publish(entry)

        # Return final OAuth location
        return self.oauth.complete(result)

    def publish(self, event):
        entry = event.get_entry()
        return self.event_bus.publish(entry)

    def resolve(self, event):
        # Get data
        payload = event.get_payload()
        data = json.dumps(payload) if payload else ""

        # Clone request object
        request = json.loads(json.dumps(event.request))

        # Resolve
        result = self.sigv4signer.resolve(request, data)
        return result

    def verify(self, event):
        signature = event.get_header("x-slack-signature")
        ts = event.get_header("x-slack-request-timestamp")
        body = event.get_body()
        return self.signer.verify(signature, ts, body)


@dataclass
class OAuth:
    client_id: str = os.getenv("SLACK_OAUTH_CLIENT_ID")
    client_secret: str = os.getenv("SLACK_OAUTH_CLIENT_SECRET")
    error_uri: str = os.getenv("SLACK_OAUTH_ERROR_URI")
    redirect_uri: str = os.getenv("SLACK_OAUTH_REDIRECT_URI")
    scope: str = os.getenv("SLACK_OAUTH_SCOPE")
    success_uri: str = os.getenv("SLACK_OAUTH_SUCCESS_URI")
    user_scope: str = os.getenv("SLACK_OAUTH_USER_SCOPE")

    def complete(self, result):
        app_id = result.get("app_id")
        team_id = result.get("team", {}).get("id")
        channel_id = result.get("incoming_webhook", {}).get("channel_id")
        success_uri = self.success_uri or "slack://open?team={TEAM_ID}"
        location = success_uri.format(
            APP_ID=app_id or "",
            TEAM_ID=team_id or "",
            CHANNEL_ID=channel_id or "",
        )
        return location

    def generate_state(self, ts=None):
        ts = ts or int(time())
        data = f"{ts}".encode()
        secret = self.client_secret.encode()
        hex = hmac.new(secret, data, sha256).hexdigest()
        state = f"{ts}.{hex}"
        return state

    def verify_state(self, state):
        ts, given = state.split(".")
        _, expected = self.generate_state(int(ts)).split(".")
        return given == expected

    @property
    def install_uri(self):
        query = {
            "client_id": self.client_id,
            "scope": self.scope,
            "user_scope": self.user_scope,
            "state": self.generate_state(),
            "redirect_uri": self.redirect_uri,
        }
        safe_query = {k: v for k, v in query.items() if v is not None}
        querystring = urlencode(safe_query, safe="+,:")
        url = f"https://slack.com/oauth/v2/authorize?{querystring}"
        return url


@dataclass
class Signer:
    secret: str = os.getenv("SLACK_SIGNING_SECRET")
    version: str = os.getenv("SLACK_SIGNING_VERSION") or "v0"

    def sign(self, body, ts=None):
        ts = ts or str(int(time()))
        data = f"{self.version}:{ts}:{body}".encode()
        logger.debug("STRING TO SIGN %s", data.decode())
        secret = self.secret.encode()
        hex = hmac.new(secret, data, sha256).hexdigest()
        signature = f"{self.version}={hex}"
        return signature

    def verify(self, signature, ts, body):
        """
        Verify timestamp & signature of request
        """
        # Get headers
        if signature is None or ts is None:
            raise Forbidden("Missing verification headers")

        # Raise if message is older than 5min or in the future
        now = time()
        try:
            delta = int(now) - int(ts)
        except ValueError:
            raise Forbidden("Request timestamp invalid")
        if delta > 5 * 60:
            raise Forbidden("Request timestamp is too old")
        elif delta < 0:
            raise Forbidden("Request timestamp is in the future")

        # Raise if signatures do not match
        expected = self.sign(body, ts)
        logger.debug("GIVEN SIGNATURE    %s", signature)
        logger.debug("EXPECTED SIGNATURE %s", expected)
        if signature != expected:
            raise Forbidden("Invalid signature")

        return True
