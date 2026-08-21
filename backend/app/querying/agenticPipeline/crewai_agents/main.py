# """
# Example entrypoint demonstrating the orchestration flow end to end.

# Run:
#     export OPENAI_API_KEY=sk-...
#     python main.py
# """
# from __future__ import annotations

# import json
# import logging

# from crewai_agents import Message, Role, run_orchestration

# logging.basicConfig(level=logging.INFO)


# def main() -> None:
#     history = [
#         Message(role=Role.USER, content="What plans does SRMB offer for TMT bars?"),
#         Message(role=Role.ASSISTANT, content="SRMB offers Fe500D and Fe550D TMT bar grades."),
#     ]
#     current_message = (
#         "Compare Fe500D vs Fe550D on yield strength, and also tell me "
#         "the warranty period for invoice #SRMB-2291."
#     )

#     flow = run_orchestration(current_message=current_message, conversation_history=history)

#     if flow.state.error:
#         print("ERROR:", flow.state.error)
#         return

#     decision = flow.state.decision
#     plan = flow.result()

#     print("Decision:", decision.model_dump_json(indent=2))
#     print("\nPlan:")
#     print(json.dumps(plan.model_dump(), indent=2))
#     print("\nAs tuples:", plan.as_tuples())


# if __name__ == "__main__":
#     main()