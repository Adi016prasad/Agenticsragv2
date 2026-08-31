"""
Test image generation using AWS Bedrock and Stability AI.
"""
from __future__ import annotations

import base64
import io
import json
import os
from dotenv import load_dotenv
import boto3
from PIL import Image

# 👉 LOAD ENVIRONMENTAL VARIABLES (Pulls your AWS Keys from .env)
load_dotenv()

# Boto3 will automatically pick up AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY from .env
bedrock = boto3.client("bedrock-runtime", region_name="us-west-2")

try:
    print("🎨 Requesting image generation from Stability AI...")
    response = bedrock.invoke_model(
        modelId="stability.stable-image-ultra-v1:1",
        body=json.dumps({
            "prompt": "A car made out of vegetables.",
            "aspect_ratio": "1:1",
            "output_format": "png"
        })
    )

    output_body = json.loads(response["body"].read().decode("utf-8"))
    base64_output_image = output_body["images"][0]
    image_data = base64.b64decode(base64_output_image)

    # Save Image
    image = Image.open(io.BytesIO(image_data))
    image.save("image.png")
    print("🎉 SUCCESS! Image generated and saved as 'image.png'.")

except Exception as e:
    print(f"❌ Failed to generate image: {e}")