"""
Dynamic Python Execution Sandbox for Multi-Table DynamoDB Query Generation.
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
        description="The complete Python code using boto3 to query/scan the DynamoDB tables and print results to stdout.",
    )


class DynamoDBSandboxInterpreterTool(BaseTool):
    name: str = "Execute Python Code in DynamoDB Sandbox"
    description: str = (
        "Executes Python code in a sandbox with pre-loaded DynamoDB resources: "
        "'metrics_table' (OrchestrationMetrics), 'feedback_table' (FeedbackMetrics), "
        "'boto3', 'Key', 'Attr', and 'Decimal'. "
        "Always print the final result using print()."
    )
    args_schema: Type[BaseModel] = PythonSandboxInput

    def _run(self, code: str) -> str:
        metrics_table_name = os.getenv("DYNAMODB_METRICS_TABLE", "OrchestrationMetrics")
        feedback_table_name = os.getenv("FEEDBACK_TABLENAME", "FeedbackMetrics")
        region = os.getenv("AWS_REGION", "ap-south-1")

        dynamodb = boto3.resource("dynamodb", region_name=region)
        metrics_table = dynamodb.Table(metrics_table_name)
        feedback_table = dynamodb.Table(feedback_table_name)

        try:
            import pandas as pd
        except ImportError:
            pd = None

        sandbox_globals: Dict[str, Any] = {
            "boto3": boto3,
            "Key": Key,
            "Attr": Attr,
            "Decimal": Decimal,
            "metrics_table": metrics_table,
            "feedback_table": feedback_table,
            "table": metrics_table,
            "metrics_table_name": metrics_table_name,
            "feedback_table_name": feedback_table_name,
            "region": region,
            "json": json,
            "time": time,
            "pd": pd,
        }

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