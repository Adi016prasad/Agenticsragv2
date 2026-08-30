"""
Dynamic Python Execution Sandbox for Firebase / Firestore Query Generation.
"""
from __future__ import annotations
import io
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Dict, Type, Optional
from google.cloud import firestore
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

collectionName = os.getenv("COLLECTIONNAME", "")

def _get_firestore_client() -> Optional[firestore.Client]:
    try:
        from container import get_firestore_client
        return get_firestore_client()
    except Exception:
        key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        if key_path and os.path.exists(key_path):
            return firestore.Client.from_service_account_json(key_path)
        return firestore.Client(project=project_id)

class FirebaseSandboxInput(BaseModel):
    code: str = Field(
        ...,
        description="The complete Python code using Firebase Admin / Firestore client (`db`) to query/fetch data and print results to stdout.",
    )

class FirebaseSandboxInterpreterTool(BaseTool):
    name: str = "Execute Python Code in Firebase Sandbox"
    description: str = (
        "Executes Python code in a sandbox with pre-loaded Firestore client 'db', 'firestore'"
        "Write custom Firestore query logic (e.g., `db.collection('...').where(...).stream()`). "
        "Always print the final result using print()."
    )
    args_schema: Type[BaseModel] = FirebaseSandboxInput

    def _run(self, code: str) -> str:
        try:
            db = _get_firestore_client()
        except Exception as e:
            return f"Firebase Initialization Error: {str(e)}"

        try:
            import pandas as pd
        except ImportError:
            pd = None

        sandbox_globals: Dict[str, Any] = {
            "firestore": firestore,
            "db": db,
            "json": json,
            "time": time,
            "datetime": datetime,
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