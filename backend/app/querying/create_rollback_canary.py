"""
One-time script to initialize 'canary_rollbacks' collection with a dummy document.
"""
import os
from google.cloud import firestore
from dotenv import load_dotenv

load_dotenv()

key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
project_id = os.getenv("FIREBASE_PROJECT_ID")

if key_path and os.path.exists(key_path):
    db = firestore.Client.from_service_account_json(key_path)
else:
    db = firestore.Client(project=project_id)

# Write a dummy document to force-create the collection
db.collection("canary_rollbacks").document("dummy_incident").set({
    "template_id": "test_template",
    "status": "pending_agent_review",
    "rolled_back_at": "2026-08-29T00:00:00Z",
    "sample_error_traces": ["No errors, initialization placeholder."],
    "metrics_snapshot": {
        "error_rate_pct": 0.0,
        "p95_latency_ms": 0.0
    }
})

print("✅ 'canary_rollbacks' collection created successfully in your Firebase Console!")