"""
Simple pressure test for /api/v1/feedbackWrite
Hits the endpoint 100 times concurrently, alternating good/bad feedback.
"""
import concurrent.futures
import random
import time

import requests

URL = "http://localhost:8001/api/v1/feedbackWrite"
AGENT_NAME = "hybridAgent"
TOTAL_REQUESTS = 1000
CONCURRENCY = 500


def send_feedback(i: int):
    feedback = random.choice(["good", "bad"])
    payload = {
        "agentName": AGENT_NAME,
        "feedback": feedback,
    }
    try:
        resp = requests.post(URL, json=payload, timeout=10)
        return i, feedback, resp.status_code, resp.text
    except Exception as exc:
        return i, feedback, "ERROR", str(exc)


def main():
    print(f"Firing {TOTAL_REQUESTS} requests at {URL} with concurrency={CONCURRENCY}")
    start = time.time()

    good_count = 0
    bad_count = 0
    success_count = 0
    failure_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = [executor.submit(send_feedback, i) for i in range(TOTAL_REQUESTS)]

        for future in concurrent.futures.as_completed(futures):
            i, feedback, status, body = future.result()

            if feedback == "good":
                good_count += 1
            else:
                bad_count += 1

            if status == 200:
                success_count += 1
            else:
                failure_count += 1
                print(f"[{i}] FAILED | feedback={feedback} | status={status} | body={body}")

    elapsed = time.time() - start

    print("\n--- Summary ---")
    print(f"Total requests : {TOTAL_REQUESTS}")
    print(f"Good sent      : {good_count}")
    print(f"Bad sent       : {bad_count}")
    print(f"Success (200)  : {success_count}")
    print(f"Failures       : {failure_count}")
    print(f"Elapsed time   : {elapsed:.2f}s")
    print(f"Requests/sec   : {TOTAL_REQUESTS / elapsed:.2f}")


if __name__ == "__main__":
    main()