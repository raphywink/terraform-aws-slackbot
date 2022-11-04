#!/usr/bin/env python

import json
import os

import boto3

from logger import logger

AWS_API_REGION = "${ApiRegion}"
AWS_EVENT_BUS_NAME = "${EventBusName}"
AWS_EVENT_BUS_REGION = "${EventBusRegion}"
AWS_SECRET_HASH = "${SecretHash}"
AWS_SECRET_ID = "${SecretId}"
AWS_SECRET_REGION = "${SecretRegion}"


def export():
    client = boto3.client("secretsmanager", region_name=AWS_SECRET_REGION)
    params = {"SecretId": AWS_SECRET_ID}
    logger.info("secretsmanager:GetSecretSring %s", json.dumps(params))
    result = client.get_secret_value(**params)
    secret = json.loads(result["SecretString"])
    os.environ.update(**secret)
