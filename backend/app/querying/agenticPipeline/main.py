from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
import logging

from crewai_agents import SQSMetricsEmitter, run_orchestration
from agenticPipeline.history import current_message_3, history_3

logging.basicConfig(level=logging.INFO)


def main() -> None:
    history = history_3
    current_message = current_message_3

    # 1. Run the Flow
    flow = run_orchestration(current_message=current_message, conversation_history=history)

    if flow.state.error:
        print("ERROR:", flow.state.error)
        return

    # 2. Extract Results
    decision = flow.state.decision
    plan = flow.result()
    metrics = flow.state.metrics

    print("\n" + "=" * 60)
    print("🎯 ORCHESTRATION COMPLETED")
    print("=" * 60)
    print("Decision:", decision.model_dump_json(indent=2))
    print("Plan:", json.dumps(plan.model_dump(), indent=2))

    # 3. 📡 Non-blocking Push to AWS SQS
    emitter = SQSMetricsEmitter()
    emitter.emit(
        state=flow.state,
        session_id="session_user_987",
        request_id="req_001_abcd",
    )
    print("\n🚀 Metric telemetry sent to SQS for downstream batch writing.")


if __name__ == "__main__":
    main()