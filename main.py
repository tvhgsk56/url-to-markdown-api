from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
import trafilatura
import requests
from bs4 import BeautifulSoup

app = FastAPI(
    title="URL to Markdown & OpenGraph Extractor",
    description="Converts web pages into clean Markdown and extracts social metadata for LLM pipelines and apps.",
    version="1.0.0"
)

class ExtractRequest(BaseModel):
    url: HttpUrl

@app.get("/")
def health_check():
    return {"status": "ok", "message": "API is running!"}

@app.post("/extract")
def extract_url_content(data: ExtractRequest):
    target_url = str(data.url)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(target_url, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {str(e)}")

    soup = BeautifulSoup(response.text, "html.parser")
    
    title = soup.find("property", {"property": "og:title"}) or soup.find("title")
    title_text = title.get("content") if title and title.get("content") else (title.string if title else "")
    
    image = soup.find("meta", {"property": "og:image"})
    image_url = image.get("content") if image else ""
    
    description = soup.find("meta", {"property": "og:description"}) or soup.find("meta", {"name": "description"})
    desc_text = description.get("content") if description else ""

    markdown_content = trafilatura.extract(
        response.text,
        output_format="markdown",
        include_links=True,
        include_images=True
    )
    
    if not markdown_content:
        raise HTTPException(status_code=422, detail="Could not extract readable text from the provided URL.")

    return {
        "url": target_url,
        "metadata": {
            "title": title_text.strip() if title_text else None,
            "description": desc_text.strip() if desc_text else None,
            "og_image": image_url.strip() if image_url else None
        },
        "markdown": markdown_content
    }