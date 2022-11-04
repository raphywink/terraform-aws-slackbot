import json


def handler(*_):
    body = json.dumps({"ok": True})
    response = {
        "statusCode": 200,
        "body": body,
        "headers": {"content-length": len(body), "content-type": "application/json"},
    }
    return response
