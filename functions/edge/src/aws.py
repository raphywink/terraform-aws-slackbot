import json
import os
from urllib.parse import parse_qsl

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from env import AWS_API_REGION, AWS_EVENT_BUS_NAME, AWS_EVENT_BUS_REGION
from logger import logger


class EventBus:
    def __init__(self, name=None, region_name=None):
        self.name = name or AWS_EVENT_BUS_NAME
        self.region_name = region_name or AWS_EVENT_BUS_REGION
        self.client = boto3.client("events", region_name=self.region_name)

    def publish(self, entry):
        params = {
            "Entries": [{"EventBusName": self.name, "Source": "slack.com", **entry}]
        }
        logger.info("events:PutEvents %s", json.dumps(params))
        return self.client.put_events(**params)


class SigV4Signer:
    def __init__(self, region_name=None):
        self.region_name = region_name or AWS_API_REGION
        self.session = boto3.Session(region_name=AWS_API_REGION)
        self.sigv4auth = SigV4Auth(
            credentials=self.session.get_credentials(),
            service_name="execute-api",
            region_name=self.session.region_name,
        )

    def resolve(self, request, data):
        # Extract signing info
        domain_name = request["origin"]["custom"]["domainName"]
        protocol = request["origin"]["custom"]["protocol"]
        path = request["origin"]["custom"]["path"]
        uri = request["uri"]
        method = request["method"]
        querystring = request["querystring"]
        url = f"{protocol}://{domain_name}{path}{uri}"

        # Prepare AWS request
        awsparams = dict(parse_qsl(querystring))
        awsrequest = AWSRequest(method, url, None, data, awsparams)

        # Sign request
        self.sigv4auth.add_auth(awsrequest)
        for key, val in awsrequest.headers.items():
            key = key.lower()
            val = {"key": key, "value": val}
            request["headers"][key] = [val]

        # Set body
        update = {"action": "replace", "encoding": "text", "data": data}
        request["body"].update(update)

        # Return result
        return request
