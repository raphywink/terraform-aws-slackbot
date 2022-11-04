import base64
import json
import os
from time import time
from unittest import mock
from urllib.parse import urlencode

import pytest

import aws
import slackbot
from logger import logger

with mock.patch("boto3.client") as mock_client:
    mock_client.return_value.get_secret_value.return_value = {"SecretString": "{}"}
    from index import handler, bot


def get_event(method, uri, querystring=None, body=None, ts=None):
    if body:
        ts = ts or str(int(time()))
        data = base64.b64encode(body.encode()).decode()
        signature = bot.signer.sign(body, ts)
        headers = {"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": signature}
        headers = {k.lower(): [{"key": k, "value": v}] for k, v in headers.items()}
    else:
        data = ""
        headers = {}
    event = {
        "Records": [
            {
                "cf": {
                    "request": {
                        "body": {
                            "action": "read-only",
                            "data": data,
                            "encoding": "base64",
                            "inputTruncated": False,
                        },
                        "headers": headers,
                        "method": method,
                        "origin": {
                            "custom": {
                                "domainName": "example.com",
                                "path": "",
                                "protocol": "https",
                            }
                        },
                        "querystring": querystring or "",
                        "uri": uri,
                    }
                }
            }
        ]
    }
    return event


def read_event(name):
    dirname = os.path.dirname(__file__)
    filename = os.path.join(dirname, f"events/{name}.json")
    with open(filename) as stream:
        return json.load(stream)


class TestHandler:
    def setup_method(self):
        logger.logger.disabled = True

        bot.sigv4signer = aws.SigV4Signer("us-east-1")
        bot.event_bus = aws.EventBus("slackbot", "us-east-1")

        slackbot.urlopen = mock.MagicMock()
        bot.oauth.generate_state = mock.MagicMock()
        bot.oauth.verify_state = mock.MagicMock()
        bot.event_bus.client = mock.MagicMock()

        bot.oauth.generate_state.return_value = "TS.STATE"
        bot.oauth.verify_state.return_value = True

        bot.oauth.client_id = "CLIENT_ID"
        bot.oauth.client_secret = "CLIENT_SECRET"
        bot.oauth.scope = "A B C"
        bot.oauth.user_scope = "D E F"
        bot.signer.secret = "SECRET!"

    def test_error(self):
        returned = handler({})
        expected = {
            "status": "500",
            "statusDescription": "INTERNAL SERVER ERROR",
            "body": json.dumps({"ok": False}),
            "headers": {
                "content-type": [
                    {"key": "content-type", "value": "application/json; charset=utf-8"}
                ]
            },
        }
        assert returned == expected

    def test_bad_route(self):
        event = get_event("GET", "/fizz")
        returned = handler(event)
        expected = {
            "status": "403",
            "statusDescription": "FORBIDDEN",
            "body": json.dumps({"ok": False}),
            "headers": {
                "content-type": [
                    {"key": "content-type", "value": "application/json; charset=utf-8"}
                ]
            },
        }
        assert returned == expected

    def test_bad_signature(self):
        event = get_event("POST", "/callbacks", None, "{}")
        for record in event["Records"]:
            for head in record["cf"]["request"]["headers"]["x-slack-signature"]:
                head["value"] = "BAD"
        returned = handler(event)
        expected = {
            "status": "403",
            "statusDescription": "FORBIDDEN",
            "body": json.dumps({"ok": False}),
            "headers": {
                "content-type": [
                    {"key": "content-type", "value": "application/json; charset=utf-8"}
                ]
            },
        }
        assert returned == expected

    def test_future_ts(self):
        event = get_event("POST", "/callbacks", None, "{}")
        for record in event["Records"]:
            for head in record["cf"]["request"]["headers"]["x-slack-request-timestamp"]:
                head["value"] = str(int(time() + 600))
        returned = handler(event)
        expected = {
            "status": "403",
            "statusDescription": "FORBIDDEN",
            "body": json.dumps({"ok": False}),
            "headers": {
                "content-type": [
                    {"key": "content-type", "value": "application/json; charset=utf-8"}
                ]
            },
        }
        assert returned == expected

    def test_old_ts(self):
        event = get_event("POST", "/callbacks", None, "{}")
        for record in event["Records"]:
            for head in record["cf"]["request"]["headers"]["x-slack-request-timestamp"]:
                head["value"] = str(int(time() - 3600))
        returned = handler(event)
        expected = {
            "status": "403",
            "statusDescription": "FORBIDDEN",
            "body": json.dumps({"ok": False}),
            "headers": {
                "content-type": [
                    {"key": "content-type", "value": "application/json; charset=utf-8"}
                ]
            },
        }
        assert returned == expected

    def test_invalid_ts(self):
        event = get_event("POST", "/callbacks", None, "{}")
        for record in event["Records"]:
            for head in record["cf"]["request"]["headers"]["x-slack-request-timestamp"]:
                head["value"] = "BAD"
        returned = handler(event)
        expected = {
            "status": "403",
            "statusDescription": "FORBIDDEN",
            "body": json.dumps({"ok": False}),
            "headers": {
                "content-type": [
                    {"key": "content-type", "value": "application/json; charset=utf-8"}
                ]
            },
        }
        assert returned == expected

    def test_bad_headers(self):
        event = get_event("POST", "/callbacks", None, "{}")
        for record in event["Records"]:
            del record["cf"]["request"]["headers"]["x-slack-request-timestamp"]
            del record["cf"]["request"]["headers"]["x-slack-signature"]
        returned = handler(event)
        expected = {
            "status": "403",
            "statusDescription": "FORBIDDEN",
            "body": json.dumps({"ok": False}),
            "headers": {
                "content-type": [
                    {"key": "content-type", "value": "application/json; charset=utf-8"}
                ]
            },
        }
        assert returned == expected

    def test_any_health(self):
        event = get_event("GET", "/health")
        returned = handler(event)
        assert "x-amz-date" in returned["headers"]
        assert "authorization" in returned["headers"]

    def test_any_install(self):
        event = get_event("GET", "/install")
        returned = handler(event)
        assert returned["status"] == "302"
        assert returned["headers"]["location"][0]["value"] == (
            "https://slack.com/oauth/v2/authorize?"
            "client_id=CLIENT_ID&"
            "scope=A+B+C&"
            "user_scope=D+E+F&state=TS.STATE"
        )

    def test_any_oauth(self):
        slackbot.urlopen.return_value.read.return_value.decode.return_value = (
            json.dumps(
                {
                    "ok": True,
                    "app_id": "APP_ID",
                    "team": {"id": "TEAM_ID"},
                    "incoming_webhook": {"channel_id": "CHANNEL_ID"},
                }
            )
        )
        event = get_event("GET", "/oauth", "code=CODE&state=STATE")
        returned = handler(event)
        assert returned["status"] == "302"
        for header in returned["headers"]["location"]:
            assert header["value"] == "slack://open?team=TEAM_ID"

    def test_post_callbacks_block_actions(self):
        data = read_event("block_actions")
        body = urlencode({"payload": json.dumps(data)})
        event = get_event("POST", "/callbacks", None, body)
        returned = handler(event)
        assert json.loads(returned["body"]["data"]) == data
        bot.event_bus.client.put_events.assert_called_once_with(
            Entries=[
                {
                    "EventBusName": "slackbot",
                    "Source": "slack.com",
                    "DetailType": "block_actions",
                    "Detail": json.dumps(
                        {"discriminator": ["action_id"], "payload": data}
                    ),
                }
            ]
        )

    @pytest.mark.parametrize("name", ["view_closed", "view_submission"])
    def test_post_callbacks_view(self, name):
        data = read_event(name)
        body = urlencode({"payload": json.dumps(data)})
        event = get_event("POST", "/callbacks", None, body)
        returned = handler(event)
        assert json.loads(returned["body"]["data"]) == data
        bot.event_bus.client.put_events.assert_called_once_with(
            Entries=[
                {
                    "EventBusName": "slackbot",
                    "Source": "slack.com",
                    "DetailType": name,
                    "Detail": json.dumps(
                        {"discriminator": "my_callback", "payload": data}
                    ),
                }
            ]
        )

    def test_post_events_verification(self):
        data = read_event("url_verification")
        body = json.dumps(data)
        event = get_event("POST", "/events", None, body)
        returned = handler(event)
        expected = {
            "status": "200",
            "statusDescription": "OK",
            "body": json.dumps({"challenge": "<challenge>"}),
            "headers": {
                "content-type": [
                    {"key": "content-type", "value": "application/json; charset=utf-8"}
                ]
            },
        }
        assert returned == expected
        bot.event_bus.client.put_events.assert_called_once_with(
            Entries=[
                {
                    "EventBusName": "slackbot",
                    "Source": "slack.com",
                    "DetailType": "url_verification",
                    "Detail": json.dumps({"discriminator": None, "payload": data}),
                }
            ]
        )

    def test_post_events(self):
        data = read_event("event_callback")
        body = json.dumps(data)
        event = get_event("POST", "/events", None, body)
        returned = handler(event)
        expected = {
            "status": "200",
            "statusDescription": "OK",
            "body": "",
            "headers": {
                "content-type": [
                    {"key": "content-type", "value": "application/json; charset=utf-8"}
                ]
            },
        }
        assert returned == expected
        bot.event_bus.client.put_events.assert_called_once_with(
            Entries=[
                {
                    "EventBusName": "slackbot",
                    "Source": "slack.com",
                    "DetailType": "event_callback",
                    "Detail": json.dumps(
                        {"discriminator": "app_home_opened", "payload": data}
                    ),
                }
            ]
        )

    def test_post_menus(self):
        data = read_event("block_suggestion")
        body = urlencode({"payload": json.dumps(data)})
        event = get_event("POST", "/menus", None, body)
        returned = handler(event)
        assert json.loads(returned["body"]["data"]) == data
        bot.event_bus.client.put_events.assert_called_once_with(
            Entries=[
                {
                    "EventBusName": "slackbot",
                    "Source": "slack.com",
                    "DetailType": "block_suggestion",
                    "Detail": json.dumps(
                        {"discriminator": "action_id", "payload": data}
                    ),
                }
            ]
        )

    def test_post_slash(self):
        data = read_event("slash_command")
        body = urlencode(data)
        event = get_event("POST", "/slash.my-command", None, body)
        returned = handler(event)
        assert json.loads(returned["body"]["data"]) == data
        bot.event_bus.client.put_events.assert_called_once_with(
            Entries=[
                {
                    "EventBusName": "slackbot",
                    "Source": "slack.com",
                    "DetailType": "slash_command",
                    "Detail": json.dumps(
                        {"discriminator": "/my-command", "payload": data}
                    ),
                }
            ]
        )
