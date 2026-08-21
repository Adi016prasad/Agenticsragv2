from crewai import Crew, Task

from agents import AgenticDataRetrievalAgentFactory
from config import OrchestrationConfig


def main():

    config = OrchestrationConfig(
        verbose=True,
    )

    agent = AgenticDataRetrievalAgentFactory(config).build()

    task = Task(
        description="""
        Calculate the average semantic latency from these records:

        [
            {"search_type": "semantic", "latency": 420},
            {"search_type": "semantic", "latency": 510},
            {"search_type": "semantic", "latency": 370},
            {"search_type": "hybrid", "latency": 800},
            {"search_type": "hybrid", "latency": 600}
        ]

        Only use semantic records.

        You MUST:
        1. Write Python code to perform the calculation.
        2. Execute the generated Python code using the execution tool.
        3. Inspect the execution result.
        4. Return the final average.

        Do not calculate the answer directly without executing Python.
        """,

        expected_output="""
        Return the average semantic latency.
        """,

        agent=agent,
    )

    crew = Crew(
        agents=[agent],
        tasks=[task],
        verbose=True,
    )

    # ========================================================
    # RUN AGENT
    # ========================================================

    result = crew.kickoff()

    # ========================================================
    # FINAL ANSWER
    # ========================================================

    print("\n" + "=" * 80)
    print("FINAL ANSWER")
    print("=" * 80)
    print(result)

    # ========================================================
    # TOKEN USAGE
    # ========================================================

    print("\n" + "=" * 80)
    print("TOKEN USAGE")
    print("=" * 80)

    usage = getattr(result, "token_usage", None)

    if usage:
        print(f"Total tokens:       {getattr(usage, 'total_tokens', 'N/A')}")
        print(f"Prompt tokens:      {getattr(usage, 'prompt_tokens', 'N/A')}")
        print(f"Completion tokens:  {getattr(usage, 'completion_tokens', 'N/A')}")
        print(f"Cached prompt:      {getattr(usage, 'cached_prompt_tokens', 'N/A')}")
    else:
        print("Token usage information is not available.")

    print("=" * 80)


if __name__ == "__main__":
    main()