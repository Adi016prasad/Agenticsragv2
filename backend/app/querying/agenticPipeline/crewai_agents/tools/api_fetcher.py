"""
CrewAI Tool that fetches telemetry metrics by calling the FastAPI backend.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Type, Any

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class FetchMetricsAPIInput(BaseModel):
    hours: float = Field(
        default=0.25,
        description="Number of hours to look back (e.g. 0.25 for 15 minutes, 1.0 for 1 hour).",
    )


class FetchMetricsFromAPITool(BaseTool):
    name: str = "Fetch Orchestration Telemetry from API"
    description: str = (
        "Calls the telemetry endpoint to retrieve latency, token usages, "
        "and error stats in dense TOON format for the last N hours."
    )
    args_schema: Type[BaseModel] = FetchMetricsAPIInput

    def _run(self, hours: float = 0.25) -> str:
        api_base_url = os.getenv("TELEMETRY_API_BASE_URL", "http://localhost:8000")
        url = f"{api_base_url}/api/v1/telemetry/metrics"

        try:
            response = requests.get(url, params={"hours": hours}, timeout=15)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            logger.error(f"API request failed: {exc}")
            return f"Error: Failed to fetch metrics from API ({exc})."

class FetchMetricsOfFeedbackFromAPITool(BaseTool):
    name : str = "Fetch Orchestration feedback from API"
    description: str = (
            "Calls the feedback endpoint to retrieve the good and bad feedback count of particular agent"
        )
    
    def _run(self) -> Any :
        api_base_url = os.getenv("TELEMETRY_API_BASE_URL", "http://localhost:8000")
        url = f"{api_base_url}/api/v1/telemetry/feedback"

        try:
            response = requests.get(url, timeout = 15)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            logger.error(f"API request failed: {exc}")
            return f"Error Failed to fetch metrics from API ({exc})."