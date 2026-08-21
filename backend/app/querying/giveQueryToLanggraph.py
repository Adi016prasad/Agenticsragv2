import os
import re
from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"], # React default ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def sanitize_client_name(name: str) -> str:
    # Lowercase, replace spaces/invalid chars with hyphens, collapse repeats
    name = name.strip().lower()
    name = re.sub(r'[^a-z0-9\-]+', '-', name)
    name = re.sub(r'-+', '-', name).strip('-')
    if not name:
        raise HTTPException(status_code=400, detail="Invalid client name")
    return name

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...), client_name: str = Form(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    safe_client = sanitize_client_name(client_name)

    try:
        bucket_name = "equity-pdf-stream-storage"
        key = f"{safe_client}/{file.filename}"
        response = s3_client.upload_fileobj(file.file, bucket_name, key)
        print(response)
        return {
            "message": f"File uploaded successfully under client '{safe_client}' Processing started!",
            "filename": file.filename,
            "s3_key": key
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to S3: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("uploadDocumentToS3Bucket:app", host = "0.0.0.0", port = 8000, reload = True)