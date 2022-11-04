"""
CloudFront Events
"""
import base64
import json
from urllib.parse import parse_qsl


class CloudFrontEvent:
    """
    Handler for a CloudFront request event
    """

    def __init__(self, request):
        self.request = request

    def get_body(self):
        """
        Get Base64-decoded body from request
        """
        data = self.request["body"]["data"]
        encoding = self.request["body"]["encoding"]
        if encoding.lower() == "base64":
            return base64.b64decode(data).decode()
        return data  # pragma: no cover

    def get_header(self, header, default=None):
        """
        Get header from request
        """
        headers = self.request["headers"].get(header) or []
        for header in headers:
            return header["value"]
        return default  # pragma: no cover

    def get_query(self):
        """
        Get query from request
        """
        return dict(parse_qsl(self.request["querystring"]))

    def get_payload(self):
        return None


class SlackEvent(CloudFrontEvent):
    def get_detail_type(self):
        """
        Get EventBridge DetailType field
        """
        payload = self.get_payload()
        return payload.get("type")

    def get_detail(self):
        """
        Get EventBridge Detail field
        """
        discriminator = self.get_discriminator()
        payload = self.get_payload()
        detail = {"discriminator": discriminator, "payload": payload}
        return detail

    def get_entry(self):
        """
        Get EventBridge entry
        """
        detail_type = self.get_detail_type()
        detail = self.get_detail()
        entry = {"DetailType": detail_type, "Detail": json.dumps(detail)}
        return entry

    def get_payload(self):
        """
        Get EventBridge Detail payload
        """
        body = self.get_body()
        return json.loads(body) if body else None


class Callback(SlackEvent):
    def get_discriminator(self):
        detail_type = self.get_detail_type()
        payload = self.get_payload()
        try:
            if detail_type == "block_actions":
                return [x["action_id"] for x in payload["actions"]]
            elif detail_type == "view_closed":
                return payload["view"]["callback_id"]
            elif detail_type == "view_submission":
                return payload["view"]["callback_id"]
            # interactive_message/message_action/shortcut
            return payload["callback_id"]
        except KeyError:
            return None

    def get_payload(self):
        body = self.get_body()
        payload = json.loads(dict(parse_qsl(body))["payload"])
        return payload


class Event(SlackEvent):
    def get_discriminator(self):
        payload = self.get_payload()
        try:
            return payload["event"]["type"]
        except KeyError:
            return None


class Menu(Callback):
    def get_discriminator(self):
        payload = self.get_payload()
        try:
            return payload["action_id"]
        except KeyError:  # pragma: no cover
            return None


class OAuth(SlackEvent):
    ...


class Slash(SlackEvent):
    def get_detail_type(self):
        return "slash_command"

    def get_discriminator(self):
        payload = self.get_payload()
        try:
            return payload["command"]
        except KeyError:  # pragma: no cover
            return None

    def get_payload(self):
        body = self.get_body()
        detail = dict(parse_qsl(body))
        return detail
