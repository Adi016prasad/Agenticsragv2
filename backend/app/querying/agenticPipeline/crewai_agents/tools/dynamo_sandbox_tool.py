"""
Dynamic Python Execution Sandbox for DynamoDB Query Generation.
"""
from __future__ import annotations

import io
import json
import logging
import os
import sys
import time
import traceback
from decimal import Decimal
from typing import Any, Dict, Type

import boto3
from boto3.dynamodb.conditions import Attr, Key
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class PythonSandboxInput(BaseModel):
    code: str = Field(
        ...,
        description="The complete Python code using boto3 to query/scan the table and print results to stdout.",
    )


class DynamoDBSandboxInterpreterTool(BaseTool):
    name: str = "Execute Python Code in DynamoDB Sandbox"
    description: str = (
        "Executes Python code in a sandbox with pre-loaded 'boto3', 'Key', 'Attr', and DynamoDB 'table'. "
        "Write custom query/scan logic using KeyConditionExpression or FilterExpression. "
        "Always print the final result using print()."
    )
    args_schema: Type[BaseModel] = PythonSandboxInput

    def _run(self, code: str) -> str:
        table_name = os.getenv("DYNAMODB_METRICS_TABLE", "OrchestrationMetrics")
        region = os.getenv("AWS_REGION", "ap-south-1")

        dynamodb = boto3.resource("dynamodb", region_name=region)
        table = dynamodb.Table(table_name)

        try:
            import pandas as pd
        except ImportError:
            pd = None

        sandbox_globals: Dict[str, Any] = {
            "boto3": boto3,
            "Key": Key,
            "Attr": Attr,
            "Decimal": Decimal,
            "table": table,
            "table_name": table_name,
            "region": region,
            "json": json,
            "time": time,
            "pd": pd,
        }

        # Strip markdown wrappers if present
        clean_code = code.strip()
        if clean_code.startswith("```python"):
            clean_code = clean_code[9:]
        if clean_code.startswith("```"):
            clean_code = clean_code[3:]
        if clean_code.endswith("```"):
            clean_code = clean_code[:-3]
        clean_code = clean_code.strip()

        old_stdout = sys.stdout
        redirected_output = io.StringIO()
        sys.stdout = redirected_output

        try:
            exec(clean_code, sandbox_globals)
            output = redirected_output.getvalue()
            return output if output.strip() else "(Code executed successfully with no print output)."
        except Exception:
            return f"Execution Error:\n{traceback.format_exc()}"
        finally:
            sys.stdout = old_stdout