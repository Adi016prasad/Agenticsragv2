"""
Executable script to run the 15-minute Metric Collector Agent.
"""
from __future__ import annotations

import logging
from dotenv import load_dotenv

load_dotenv()

from crewai_agents.config import DEFAULT_CONFIG
from crewai_agents.evaluation_crew import MetricEvaluationCrew

logging.basicConfig(level=logging.INFO)


def main() -> None:
    print("\n🔍 Triggering 15-Minute Metric Collector Agent...\n")
    
    eval_crew = MetricEvaluationCrew(config=DEFAULT_CONFIG)
    report = eval_crew.evaluate(lookback_hours=3.0)

    print("\n" + "=" * 70)
    print("📋 EXECUTIVE PERFORMANCE SUMMARY")
    print("=" * 70)
    print(f"\n📝 Narrative Summary:\n{report.evaluation_summary_narrative}")
    print("\n" + "-" * 70)
    print(f"\n🎯 Optimization Recommendations:\n{report.optimization_recommendations}")
    print("=" * 70)


if __name__ == "__main__":
    main()