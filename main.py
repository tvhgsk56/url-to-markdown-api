import os
import socket
from ipaddress import ip_address
from urllib.parse import urlparse
from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, HttpUrl
import trafilatura
import requests
from bs4 import BeautifulSoup
app = FastAPI(
    title="URL to Markdown & OpenGraph Extractor",
    description="Converts web pages into clean Markdown and extracts social metadata for LLM pipelines and apps.",
    version="1.0.0"
)
def validate_url_security(target_url: str) -> str:
    """Validates URL protocol and prevents SSRF by blocking private IP targets."""
    parsed = urlparse(target_url)
    
    # Enforce HTTP/HTTPS only
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL scheme. Only http and https are allowed."
        )

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL hostname."
        )

    # Prevent explicit localhost access
    if hostname.lower() in ("localhost", "127.0.0.1", "0.0.0.0"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Access to internal/local addresses is forbidden."
        )

    # Resolve DNS hostname and inspect IP address
    try:
        resolved_ip = socket.gethostbyname(hostname)
        ip_obj = ip_address(resolved_ip)
        
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Access to private or local IP ranges is forbidden."
            )
    except socket.gaierror:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not resolve target domain name."
        )

    return target_url
EXPECTED_SECRET = os.getenv("RAPIDAPI_PROXY_SECRET")
class ExtractRequest(BaseModel):
    url: str

@app.get("/")
def health_check():
    return {"status": "ok", "message": "API is running!"}

@app.post("/extract")
def extract_url_content(data: ExtractRequest, x_rapidapi_proxy_secret: str = Header(None)):
    if x_rapidapi_proxy_secret != EXPECTED_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Requests must go through RapidAPI."
        )

    raw_url = str(data.url).strip()
    target_url = validate_url_security(raw_url)
    
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
@app.get("")
@app.get("/")
@app.head("")
@app.head("/")
async def root():
    return {"message": "API is running"}
