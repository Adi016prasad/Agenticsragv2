# """
# Stage 3 Engine: Bulletproof Ragas Benchmark Engine.
# Handles API changes dynamically to guarantee 0 crashes.
# """
# from __future__ import annotations

# import sys
# import types
# from unittest.mock import MagicMock

# # Bypass unused VertexAI import in ragas
# if "langchain_community.chat_models.vertexai" not in sys.modules:
#     mod = types.ModuleType("langchain_community.chat_models.vertexai")
#     mod.ChatVertexAI = MagicMock()
#     sys.modules["langchain_community.chat_models.vertexai"] = mod

# import csv
# import io
# import json
# import logging
# import os
# import smtplib
# from email.mime.text import MIMEText
# from typing import Any, Dict, Optional

# from storage import StorageFactory
# from datasets import Dataset
# from ragas import evaluate
# from ragas.metrics._faithfulness import Faithfulness
# from ragas.metrics._context_precision import LLMContextPrecisionWithReference
# from langchain_openai import ChatOpenAI
# from dotenv import load_dotenv

# load_dotenv()

# logger = logging.getLogger(__name__)


# def _get_evaluator_llm() -> ChatOpenAI:
#     """Uses the fast GPT OSS Safeguard 20B model on Bedrock Mantle with high timeout tolerance."""
#     return ChatOpenAI(
#         model="openai.gpt-oss-safeguard-20b",
#         api_key=os.getenv("APIKEYFORBEDROCK"),
#         base_url=os.getenv(
#             "BEDROCK_MANTLE_BASE_URL",
#             "https://bedrock-mantle.ap-south-1.api.aws/v1",
#         ),
#         default_headers={"OpenAI-Project": "default"},
#         timeout=240,       # 4-minute timeout to easily survive Bedrock queuing
#         max_retries=10,    # High retries to prevent throttling drops
#         temperature=0.0
#     )


# class RagasBenchmarkEngine:
#     def __init__(self) -> None:
#         self._storage = StorageFactory.create_storage()

#     def run_ragas_evaluation(self, eval_run_id: str) -> Optional[Dict[str, float]]:
#         stage2_key = f"benchmarks/run_{eval_run_id}/stage2_enriched_dataset.csv"

#         logger.info(f"📥 Stage 3: Downloading '{stage2_key}' from S3...")
#         csv_text = self._storage.download_csv(stage2_key)

#         if not csv_text:
#             logger.error(f"❌ Enriched dataset not found at: {stage2_key}")
#             return None

#         reader = csv.DictReader(io.StringIO(csv_text))
#         user_inputs, references, contexts_list, responses = [], [], [], []

#         for row in reader:
#             user_inputs.append(row["user_input"])
#             references.append(row["reference"])
#             responses.append(row["response"])
#             try:
#                 chunks = json.loads(row["retrieved_contexts"])
#             except Exception:
#                 chunks = [row["retrieved_contexts"]]
#             contexts_list.append(chunks)

#         logger.info(f"🧪 Running Ragas evaluation on {len(user_inputs)} samples...")

#         try:
#             eval_dict = {
#                 "user_input": user_inputs,
#                 "reference": references,
#                 "retrieved_contexts": contexts_list,
#                 "response": responses,
#             }
#             dataset = Dataset.from_dict(eval_dict)
#             evaluator_llm = _get_evaluator_llm()

#             # ---------------------------------------------------------
#             # 🛡️ BULLETPROOF RAGAS EXECUTION (Immune to TypeErrors)
#             # ---------------------------------------------------------
#             eval_kwargs = {
#                 "dataset": dataset,
#                 "metrics": [
#                     Faithfulness(),
#                     LLMContextPrecisionWithReference()
#                 ],
#                 "llm": evaluator_llm,
#             }

#             # Attempt to use the modern Ragas RunConfig for concurrency limiting
#             try:
#                 from ragas.run_config import RunConfig
#                 eval_kwargs["run_config"] = RunConfig(max_workers=2, timeout=240)
#             except ImportError:
#                 pass # Fallback safely if RunConfig is missing in this version

#             try:
#                 results = evaluate(**eval_kwargs)
#             except TypeError:
#                 # Absolute fallback: Strip kwargs to bare minimum to guarantee execution
#                 eval_kwargs.pop("run_config", None)
#                 results = evaluate(**eval_kwargs)

#             # ---------------------------------------------------------
            
#             df = results.to_pandas()

#             scores = {
#                 "faithfulness": round(float(df["faithfulness"].mean()), 3) if "faithfulness" in df else 0.0,
#                 "context_precision": round(float(df["context_precision"].mean()), 3) if "context_precision" in df else 0.0,
#                 "context_recall": round(float(df["context_recall"].mean()), 3) if "context_recall" in df else 0.0,
#             }

#             logger.info(f"✅ RAGAS Scoring Complete via Bedrock Mantle: {scores}")
#             self._send_scorecard_email(eval_run_id, scores, len(user_inputs), stage2_key)
#             return scores

#         except Exception as exc:
#             logger.error(f"❌ Ragas evaluation failed: {exc}", exc_info=True)
#             return None

#     def _send_scorecard_email(self, eval_run_id: str, scores: Dict[str, float], total_queries: int, s3_path: str) -> None:
#         smtp_host = os.getenv("SMTP_HOST")
#         smtp_port = int(os.getenv("SMTP_PORT", "587"))
#         smtp_user = os.getenv("SMTP_USER")
#         smtp_password = os.getenv("SMTP_PASSWORD")
#         approver_email = os.getenv("APPROVER_EMAIL")
#         bucket_name = os.getenv("EVAL_S3_BUCKET_NAME", "agenticrag-eval-bucket")

#         if not all([smtp_host, smtp_user, smtp_password, approver_email]):
#             logger.warning("SMTP configuration missing. Skipping scorecard email.")
#             return

#         subject = f"📊 [RAGAS Benchmark] RAG Quality Scorecard: {eval_run_id}"
#         f_score = scores.get("faithfulness", 0.0)
#         p_score = scores.get("context_precision", 0.0)
#         r_score = scores.get("context_recall", 0.0)
#         status = "🟢 HEALTHY (SLA Met)" if f_score >= 0.85 and p_score >= 0.80 else "🟡 DEGRADED (Tuning Needed)"

#         body = (
#             f"============================================================\n"
#             f"🧪 RAGAS PIPELINE CONTINUOUS EVALUATION SCORECARD\n"
#             f"============================================================\n"
#             f"Run ID: {eval_run_id}\n"
#             f"Status: {status}\n"
#             f"Evaluated Queries: {total_queries} test cases\n"
#             f"S3 Dataset Path: s3://{bucket_name}/{s3_path}\n\n"
#             f"📊 MATHEMATICAL RAGAS SCORES (Target >= 0.85):\n"
#             f"• Faithfulness (Hallucination Index):  {f_score:.3f}\n"
#             f"• Context Precision (Qdrant Ranking):   {p_score:.3f}\n"
#             f"• Context Recall (Document Coverage):  {r_score:.3f}\n\n"
#             f"🔍 SRE RECOMMENDATION:\n"
#             f"{'Qdrant precision is below 0.80. Consider increasing score_threshold or tuning top_k in .env.' if p_score < 0.80 else 'All retrieval and generation metrics meet production SLAs.'}\n"
#             f"============================================================\n"
#         )

#         msg = MIMEText(body)
#         msg["Subject"] = subject
#         msg["From"] = smtp_user
#         msg["To"] = approver_email

#         try:
#             with smtplib.SMTP(smtp_host, smtp_port) as server:
#                 server.starttls()
#                 server.login(smtp_user, smtp_password)
#                 server.sendmail(smtp_user, [approver_email], msg.as_string())
#             logger.info(f"📧 Ragas Scorecard Email successfully sent to {approver_email}")
#         except Exception as e:
#             logger.error(f"Failed to send email: {e}")
"""
Stage 3 Engine: Bulletproof Ragas Benchmark Engine.
Optimized to use Deterministic Metrics (BLEU, ROUGE, ExactMatch) to slash token costs,
keeping only Faithfulness as the LLM-based hallucination judge.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

# 👉 BYPASS UNUSED VERTEXAI IMPORT IN RAGAS PERMANENTLY
if "langchain_community.chat_models.vertexai" not in sys.modules:
    mod = types.ModuleType("langchain_community.chat_models.vertexai")
    mod.ChatVertexAI = MagicMock()
    sys.modules["langchain_community.chat_models.vertexai"] = mod

import csv
import io
import json
import logging
import os
import smtplib
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

from storage import StorageFactory
from datasets import Dataset
from ragas import evaluate

# 1 LLM Metric + 3 Deterministic (0 Token) Metrics
from ragas.metrics._faithfulness import Faithfulness
from ragas.metrics._string import ExactMatch
from ragas.metrics._bleu_score import BleuScore
from ragas.metrics._rouge_score import RougeScore

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


def _get_evaluator_llm() -> ChatOpenAI:
    """Uses the fast GPT OSS Safeguard 20B model on Bedrock Mantle with high timeout tolerance."""
    return ChatOpenAI(
        model=os.getenv("BEDROCK_MANTLE_AGENTIC_MODEL", "openai.gpt-oss-safeguard-20b"),
        api_key=os.getenv("APIKEYFORBEDROCK"),
        base_url=os.getenv(
            "BEDROCK_MANTLE_BASE_URL",
            "https://bedrock-mantle.ap-south-1.api.aws/v1",
        ),
        default_headers={"OpenAI-Project": "default"},
        timeout=240,       # 4-minute timeout to easily survive Bedrock queuing
        max_retries=10,    # High retries to prevent throttling drops
        temperature=0.0
    )


class RagasBenchmarkEngine:
    def __init__(self) -> None:
        self._storage = StorageFactory.create_storage()

    def run_ragas_evaluation(self, eval_run_id: str) -> Optional[Dict[str, float]]:
        stage2_key = f"benchmarks/run_{eval_run_id}/stage2_enriched_dataset.csv"

        logger.info(f"📥 Stage 3: Downloading '{stage2_key}' from S3...")
        csv_text = self._storage.download_csv(stage2_key)

        if not csv_text:
            logger.error(f"❌ Enriched dataset not found at: {stage2_key}")
            return None

        reader = csv.DictReader(io.StringIO(csv_text))
        user_inputs, references, contexts_list, responses = [], [], [], []

        for row in reader:
            user_inputs.append(row["user_input"])
            references.append(row["reference"])
            responses.append(row["response"])
            try:
                chunks = json.loads(row["retrieved_contexts"])
            except Exception:
                chunks = [row["retrieved_contexts"]]
            contexts_list.append(chunks)

        logger.info(f"🧪 Running Cost-Optimized Ragas evaluation on {len(user_inputs)} samples...")

        try:
            eval_dict = {
                "user_input": user_inputs,
                "reference": references,
                "retrieved_contexts": contexts_list,
                "response": responses,
            }
            dataset = Dataset.from_dict(eval_dict)
            evaluator_llm = _get_evaluator_llm()

            # ---------------------------------------------------------
            # 🛡️ COST-OPTIMIZED & BULLETPROOF RAGAS EXECUTION
            # ---------------------------------------------------------
            eval_kwargs = {
                "dataset": dataset,
                "metrics": [
                    Faithfulness(),  # The only LLM call
                    ExactMatch(),    # 0 tokens
                    BleuScore(),     # 0 tokens
                    RougeScore(),    # 0 tokens
                ],
                "llm": evaluator_llm,
            }

            # Attempt to use the modern Ragas RunConfig for concurrency limiting
            try:
                from ragas.run_config import RunConfig
                eval_kwargs["run_config"] = RunConfig(max_workers=2, timeout=240)
            except ImportError:
                pass # Fallback safely if RunConfig is missing in this version

            try:
                results = evaluate(**eval_kwargs)
            except TypeError:
                # Absolute fallback: Strip kwargs to bare minimum to guarantee execution
                eval_kwargs.pop("run_config", None)
                results = evaluate(**eval_kwargs)

            # ---------------------------------------------------------
            
            df = results.to_pandas()

            # Extract new deterministic scores
            scores = {
                "faithfulness": round(float(df["faithfulness"].mean()), 3) if "faithfulness" in df else 0.0,
                "exact_match": round(float(df["exact_match"].mean()), 3) if "exact_match" in df else 0.0,
                "bleu_score": round(float(df["bleu_score"].mean()), 3) if "bleu_score" in df else 0.0,
                "rouge_score": round(float(df["rouge_score"].mean()), 3) if "rouge_score" in df else 0.0,
            }

            logger.info(f"✅ RAGAS Scoring Complete via Bedrock Mantle: {scores}")
            self._send_scorecard_email(eval_run_id, scores, len(user_inputs), stage2_key)
            return scores

        except Exception as exc:
            logger.error(f"❌ Ragas evaluation failed: {exc}", exc_info=True)
            return None

    def _send_scorecard_email(self, eval_run_id: str, scores: Dict[str, float], total_queries: int, s3_path: str) -> None:
        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")
        approver_email = os.getenv("APPROVER_EMAIL")
        bucket_name = os.getenv("EVAL_S3_BUCKET_NAME", "agenticrag-eval-bucket")

        if not all([smtp_host, smtp_user, smtp_password, approver_email]):
            logger.warning("SMTP configuration missing. Skipping scorecard email.")
            return

        subject = f"📊 [RAGAS Benchmark] Optimized RAG Scorecard: {eval_run_id}"
        
        f_score = scores.get("faithfulness", 0.0)
        # Lexical matches (BLEU/ROUGE) are typically lower than semantic matches. 
        # A BLEU score > 0.20 is usually acceptable for open-ended RAG.
        b_score = scores.get("bleu_score", 0.0)
        status = "🟢 HEALTHY (SLA Met)" if f_score >= 0.85 else "🟡 DEGRADED (Hallucinations Detected)"

        body = (
            f"============================================================\n"
            f"🧪 RAGAS PIPELINE CONTINUOUS EVALUATION SCORECARD\n"
            f"============================================================\n"
            f"Run ID: {eval_run_id}\n"
            f"Status: {status}\n"
            f"Evaluated Queries: {total_queries} test cases\n"
            f"S3 Dataset Path: s3://{bucket_name}/{s3_path}\n\n"
            f"📊 HYBRID EVALUATION SCORES:\n"
            f"--- LLM Metric (Target >= 0.85) ---\n"
            f"• Faithfulness (Hallucination Index):  {f_score:.3f}\n\n"
            f"--- Deterministic String Metrics (0 Token Cost) ---\n"
            f"• BLEU Score (N-gram Overlap):         {b_score:.3f}\n"
            f"• ROUGE Score (Recall Overlap):        {scores.get('rouge_score'):.3f}\n"
            f"• Exact Match (Verbatim Accuracy):     {scores.get('exact_match'):.3f}\n\n"
            f"🔍 SRE RECOMMENDATION:\n"
            f"{'LLM Faithfulness is below 0.85. The model is hallucinating outside of retrieved context.' if f_score < 0.85 else 'LLM Faithfulness is healthy and grounded in the retrieved text.'}\n"
            f"Note: BLEU/ROUGE are lexical metrics. Low scores indicate paraphrasing by the LLM, not necessarily incorrect answers.\n"
            f"============================================================\n"
        )

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = approver_email

        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(smtp_user, [approver_email], msg.as_string())
            logger.info(f"📧 Optimized Ragas Scorecard Email successfully sent to {approver_email}")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")