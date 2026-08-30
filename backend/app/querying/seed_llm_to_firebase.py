"""
Seeds the 'LLM' collection in Firestore with:
1. 'currentlyactivemodel' -> The active production model details
2. 'othermodelsavailable' -> The list of all 35 other candidate models with full specs & pricing
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

from dotenv import load_dotenv
from google.cloud import firestore

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("LLMModelSeeder")


def get_client() -> firestore.Client:
    """Initializes Firestore client using application credentials."""
    try:
        from container import get_firestore_client
        return get_firestore_client()
    except Exception:
        key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        if key_path and os.path.exists(key_path):
            return firestore.Client.from_service_account_json(key_path)
        return firestore.Client(project=project_id)


# ==============================================================================
# 1. CURRENTLY ACTIVE MODEL DEFINITION
# ==============================================================================
CURRENTLY_ACTIVE_MODEL: Dict[str, Any] = {
    # 1. Master Query Orchestrator -> Voxtral Mini 3B 2507 ($0.05 / $0.05)
    "orchestrator_model": {
        "model_id": "mistral.voxtral-mini-3b-2507",
        "name": "Voxtral Mini 3B 2507",
        "input_price_per_1m": 0.05,
        "output_price_per_1m": 0.05,
    },
    # 2. Semantic & Hybrid Rewriters -> Voxtral Mini 3B 2507 ($0.05 / $0.05)
    "rewriter_model": {
        "model_id": "mistral.voxtral-mini-3b-2507",
        "name": "Voxtral Mini 3B 2507",
        "input_price_per_1m": 0.05,
        "output_price_per_1m": 0.05,
    },
    # 3. Metric Collector Agent -> Gemma 3 4B IT ($0.05 / $0.09)
    "metric_collector_model": {
        "model_id": "google.gemma-3-4b-it",
        "name": "Gemma 3 4B IT",
        "input_price_per_1m": 0.05,
        "output_price_per_1m": 0.09,
    },
    # 4. Multi-Agent Discussion Crew -> GPT OSS Safeguard 120B ($0.18 / $0.71)
    "discussion_model": {
        "model_id": "openai.gpt-oss-safeguard-120b",
        "name": "GPT OSS Safeguard 120B",
        "input_price_per_1m": 0.18,
        "output_price_per_1m": 0.71,
    },
    "is_active": True,
}


# ==============================================================================
# 2. ALL 35 OTHER CANDIDATE MODELS DEFINITION (Excluding the 2 extra ones)
# ==============================================================================
OTHER_MODELS_AVAILABLE: List[Dict[str, Any]] = [
    {
        "name": "Voxtral Mini 3B 2507",
        "model_id": "mistral.voxtral-mini-3b-2507",
        "input_price_per_1m": 0.05,
        "output_price_per_1m": 0.05,
        "max_context": "32K",
        "max_output": None,
        "modality": "Text, Audio -> Text",
    },
    {
        "name": "Gemma 3 4B IT",
        "model_id": "google.gemma-3-4b-it",
        "input_price_per_1m": 0.05,
        "output_price_per_1m": 0.09,
        "max_context": "128K",
        "max_output": "8K",
        "modality": "Text, Image -> Text",
    },
    {
        "name": "NVIDIA Nemotron Nano 9B v2",
        "model_id": "nvidia.nemotron-nano-9b-v2",
        "input_price_per_1m": 0.07,
        "output_price_per_1m": 0.27,
        "max_context": "128K",
        "max_output": "8K",
        "modality": "Text -> Text",
    },
    {
        "name": "Nemotron Nano 3 30B",
        "model_id": "nvidia.nemotron-nano-3-30b",
        "input_price_per_1m": 0.07,
        "output_price_per_1m": 0.28,
        "max_context": "256K",
        "max_output": "8K",
        "modality": "Text -> Text",
    },
    {
        "name": "GPT OSS Safeguard 20B",
        "model_id": "openai.gpt-oss-safeguard-20b",
        "input_price_per_1m": 0.08,
        "output_price_per_1m": 0.24,
        "max_context": "128K",
        "max_output": "16K",
        "modality": "Text -> Text",
    },
    {
        "name": "GPT OSS 20B",
        "model_id": "openai.gpt-oss-20b",
        "input_price_per_1m": 0.08,
        "output_price_per_1m": 0.35,
        "max_context": "128K",
        "max_output": "16K",
        "modality": "Text -> Text",
    },
    {
        "name": "GLM 4.7 Flash",
        "model_id": "zai.glm-4.7-flash",
        "input_price_per_1m": 0.08,
        "output_price_per_1m": 0.48,
        "max_context": "203K",
        "max_output": "4K",
        "modality": "Text -> Text",
    },
    {
        "name": "Gemma 3 12B IT",
        "model_id": "google.gemma-3-12b-it",
        "input_price_per_1m": 0.11,
        "output_price_per_1m": 0.34,
        "max_context": "128K",
        "max_output": "8K",
        "modality": "Text, Image -> Text",
    },
    {
        "name": "Ministral 3B",
        "model_id": "mistral.ministral-3-3b-instruct",
        "input_price_per_1m": 0.12,
        "output_price_per_1m": 0.12,
        "max_context": "128K",
        "max_output": "8K",
        "modality": "Text, Image -> Text",
    },
    {
        "name": "Voxtral Small 24B 2507",
        "model_id": "mistral.voxtral-small-24b-2507",
        "input_price_per_1m": 0.12,
        "output_price_per_1m": 0.35,
        "max_context": "32K",
        "max_output": None,
        "modality": "Text, Audio -> Text",
    },
    {
        "name": "Ministral 3 8B",
        "model_id": "mistral.ministral-3-8b-instruct",
        "input_price_per_1m": 0.18,
        "output_price_per_1m": 0.18,
        "max_context": "128K",
        "max_output": "8K",
        "modality": "Text, Image -> Text",
    },
    {
        "name": "Qwen3-Coder-30B-A3B-Instruct",
        "model_id": "qwen.qwen3-coder-30b-a3b-instruct",
        "input_price_per_1m": 0.18,
        "output_price_per_1m": 0.71,
        "max_context": "256K",
        "max_output": "16K",
        "modality": "Text -> Text",
    },
    {
        "name": "Qwen3 32B",
        "model_id": "qwen.qwen3-32b",
        "input_price_per_1m": 0.18,
        "output_price_per_1m": 0.71,
        "max_context": "32K",
        "max_output": "8K",
        "modality": "Text -> Text",
    },
    {
        "name": "GPT OSS 120B",
        "model_id": "openai.gpt-oss-120b",
        "input_price_per_1m": 0.18,
        "output_price_per_1m": 0.71,
        "max_context": "128K",
        "max_output": "16K",
        "modality": "Text -> Text",
    },
    {
        "name": "Palmyra Vision 7B",
        "model_id": "writer.palmyra-vision-7b",
        "input_price_per_1m": 0.18,
        "output_price_per_1m": 0.72,
        "max_context": "4K",
        "max_output": "4K",
        "modality": "Text, Image -> Text",
    },
    {
        "name": "NVIDIA Nemotron 3 Super 120B",
        "model_id": "nvidia.nemotron-super-3-120b",
        "input_price_per_1m": 0.18,
        "output_price_per_1m": 0.78,
        "max_context": "256K",
        "max_output": "32K",
        "modality": "Text -> Text",
    },
    {
        "name": "Qwen3 Next 80B A3B",
        "model_id": "qwen.qwen3-next-80b-a3b-instruct",
        "input_price_per_1m": 0.18,
        "output_price_per_1m": 1.41,
        "max_context": "256K",
        "max_output": "8K",
        "modality": "Text -> Text",
    },
    {
        "name": "Ministral 14B 3.0",
        "model_id": "mistral.ministral-3-14b-instruct",
        "input_price_per_1m": 0.24,
        "output_price_per_1m": 0.24,
        "max_context": "128K",
        "max_output": "8K",
        "modality": "Text, Image -> Text",
    },
    {
        "name": "Qwen3 235B A22B 2507",
        "model_id": "qwen.qwen3-235b-a22b-2507",
        "input_price_per_1m": 0.26,
        "output_price_per_1m": 1.04,
        "max_context": "256K",
        "max_output": "8K",
        "modality": "Text -> Text",
    },
    {
        "name": "Gemma 3 27B IT",
        "model_id": "google.gemma-3-27b-it",
        "input_price_per_1m": 0.27,
        "output_price_per_1m": 0.45,
        "max_context": "128K",
        "max_output": "8K",
        "modality": "Text, Image -> Text",
    },
    {
        "name": "MiniMax M2",
        "model_id": "minimax.minimax-m2",
        "input_price_per_1m": 0.35,
        "output_price_per_1m": 1.41,
        "max_context": "1M",
        "max_output": "8K",
        "modality": "Text -> Text",
    },
    {
        "name": "MiniMax M2.1",
        "model_id": "minimax.minimax-m2.1",
        "input_price_per_1m": 0.36,
        "output_price_per_1m": 1.44,
        "max_context": "196K",
        "max_output": "8K",
        "modality": "Text -> Text",
    },
    {
        "name": "MiniMax M2.5",
        "model_id": "minimax.minimax-m2.5",
        "input_price_per_1m": 0.36,
        "output_price_per_1m": 1.44,
        "max_context": "196K",
        "max_output": "8K",
        "modality": "Text -> Text",
    },
    {
        "name": "Devstral 2 123B",
        "model_id": "mistral.devstral-2-123b",
        "input_price_per_1m": 0.48,
        "output_price_per_1m": 2.40,
        "max_context": "256K",
        "max_output": "32K",
        "modality": "Text -> Text",
    },
    {
        "name": "Qwen3 Coder 480B A35B Instruct",
        "model_id": "qwen.qwen3-coder-480b-a35b-instruct",
        "input_price_per_1m": 0.53,
        "output_price_per_1m": 2.12,
        "max_context": "128K",
        "max_output": "16K",
        "modality": "Text -> Text",
    },
    {
        "name": "Magistral Small 2509",
        "model_id": "mistral.magistral-small-2509",
        "input_price_per_1m": 0.59,
        "output_price_per_1m": 1.76,
        "max_context": "128K",
        "max_output": "40K",
        "modality": "Text, Image -> Text",
    },
    {
        "name": "Mistral Large 3",
        "model_id": "mistral.mistral-large-3-675b-instruct",
        "input_price_per_1m": 0.59,
        "output_price_per_1m": 1.76,
        "max_context": "256K",
        "max_output": "32K",
        "modality": "Text, Image -> Text",
    },
    {
        "name": "Qwen3 Coder Next",
        "model_id": "qwen.qwen3-coder-next",
        "input_price_per_1m": 0.60,
        "output_price_per_1m": 1.44,
        "max_context": "256K",
        "max_output": "16K",
        "modality": "Text -> Text",
    },
    {
        "name": "Qwen3 VL 235B A22B",
        "model_id": "qwen.qwen3-vl-235b-a22b-instruct",
        "input_price_per_1m": 0.62,
        "output_price_per_1m": 3.13,
        "max_context": "256K",
        "max_output": "8K",
        "modality": "Text, Image -> Text",
    },
    {
        "name": "DeepSeek-V3.1",
        "model_id": "deepseek.v3.1",
        "input_price_per_1m": 0.68,
        "output_price_per_1m": 1.98,
        "max_context": "128K",
        "max_output": "8K",
        "modality": "Text -> Text",
    },
    {
        "name": "Kimi K2 Thinking",
        "model_id": "moonshotai.kimi-k2-thinking",
        "input_price_per_1m": 0.71,
        "output_price_per_1m": 2.94,
        "max_context": "256K",
        "max_output": "16K",
        "modality": "Text -> Text",
    },
    {
        "name": "Kimi K2.5",
        "model_id": "moonshotai.kimi-k2.5",
        "input_price_per_1m": 0.72,
        "output_price_per_1m": 3.60,
        "max_context": "256K",
        "max_output": "16K",
        "modality": "Text -> Text",
    },
    {
        "name": "GLM 4.7",
        "model_id": "zai.glm-4.7",
        "input_price_per_1m": 0.72,
        "output_price_per_1m": 2.64,
        "max_context": "203K",
        "max_output": "4K",
        "modality": "Text -> Text",
    },
    {
        "name": "DeepSeek V3.2",
        "model_id": "deepseek.v3.2",
        "input_price_per_1m": 0.74,
        "output_price_per_1m": 2.22,
        "max_context": "164K",
        "max_output": "8K",
        "modality": "Text -> Text",
    },
    {
        "name": "GLM 5",
        "model_id": "zai.glm-5",
        "input_price_per_1m": 1.20,
        "output_price_per_1m": 3.84,
        "max_context": "200K",
        "max_output": "128K",
        "modality": "Text -> Text",
    },
]


def seed_llm_collection() -> None:
    logger.info("Connecting to Firestore...")
    db = get_client()
    llm_col = db.collection("LLM")
    now_iso = datetime.now(timezone.utc).isoformat()

    logger.info("Writing 'currentlyactivemodel' document...")
    llm_col.document("currentlyactivemodel").set({
        **CURRENTLY_ACTIVE_MODEL,
        "updated_at": now_iso,
    })
    logger.info("✅ 'currentlyactivemodel' written successfully.")

    logger.info("Writing 'othermodelsavailable' document...")
    llm_col.document("othermodelsavailable").set({
        "models": OTHER_MODELS_AVAILABLE,
        "total_count": len(OTHER_MODELS_AVAILABLE),
        "updated_at": now_iso,
    })
    logger.info(f"✅ 'othermodelsavailable' written successfully with {len(OTHER_MODELS_AVAILABLE)} models.")

    print("\n" + "=" * 70)
    print("🎉 FIRESTORE 'LLM' COLLECTION SEEDED SUCCESSFULLY!")
    print("• Document 1: 'currentlyactivemodel' (GPT OSS Safeguard 120B)")
    print(f"• Document 2: 'othermodelsavailable' ({len(OTHER_MODELS_AVAILABLE)} models)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    seed_llm_collection()