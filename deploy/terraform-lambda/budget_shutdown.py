"""Disable the batch transcription Lambda when the AWS Budget limit is reached."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    target_function = os.environ["TARGET_FUNCTION_NAME"]
    lambda_client = boto3.client("lambda")

    messages: list[str] = []
    for record in event.get("Records", []):
        sns = record.get("Sns", {})
        message = sns.get("Message", "")
        messages.append(message)
        logger.warning("Budget shutdown triggered for %s: %s", target_function, message)

    lambda_client.put_function_concurrency(
        FunctionName=target_function,
        ReservedConcurrentExecutions=0,
    )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "status": "disabled",
                "function": target_function,
                "messages": messages,
            }
        ),
    }
