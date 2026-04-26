import requests
from bs4 import BeautifulSoup
from typing import Optional, Dict


def scrape_url_metadata(url: str) -> Dict[str, str]:
    """Fetches a URL and extracts its title and description metadata."""
    try:
        # Basic URL validation
        if not url.startswith("http"):
            url = "https://" + url

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        # A short timeout ensures the API responds quickly even for slow sites
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        title = soup.title.string if soup.title else ""

        description = ""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            description = meta_desc["content"]

        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            description = og_desc["content"]

        return {
            "title": title.strip() if title else "Unknown Title",
            "description": (
                description.strip() if description else "No description available"
            ),
            "url": url,
        }
    except Exception as e:
        print(f"Scraping error: {e}")
        return {
            "title": "Unknown Source",
            "description": "Failed to scrape URL",
            "url": url,
        }


def simulate_fingerprint_from_metadata(
    metadata: Dict[str, str], fallback_description: str = ""
) -> Optional[str]:
    """
    Match scraped text against known catalog keywords to return a canonical fingerprint.
    Uses Google Gemini if an API key is present, otherwise falls back to heuristics.
    """
    from data.mock_assets import get_all_assets
    import os
    import json
    import re

    url_raw = metadata.get('url', '')
    # Also scan URL path segments — helps identify events from deep links on niche sites
    # e.g. footem.site/bundesliga-live → will pick up 'bundesliga'
    from urllib.parse import urlparse, unquote
    url_path = unquote(urlparse(url_raw).path).replace("/", " ").replace("-", " ").replace("_", " ")
    combined_text = f"{metadata.get('title', '')} {metadata.get('description', '')} {fallback_description} {url_path}".lower()

    matched_asset_id = None
    api_key = os.getenv("GEMINI_API_KEY")

    if api_key:
        try:
            import requests
            assets = get_all_assets()
            catalog_summary = ", ".join(
                [f"'{a.asset_id}': {a.event_name}" for a in assets]
            )

            prompt = f"""
            You are an AI Rights Identifier.
            Map the following video text to the most relevant Asset ID from this catalog:
            {catalog_summary}.

            If the text does not clearly match any of these events, return 'UNKNOWN'.

            Video Text: "{combined_text}"

            Reply with ONLY a valid JSON object in this exact format:
            {{"asset_id": "ASSET-XXX"}}
            or
            {{"asset_id": "UNKNOWN"}}
            """

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json"
                }
            }

            res = requests.post(url, json=payload, timeout=5)
            res.raise_for_status()

            data = res.json()
            text_response = data["candidates"][0]["content"]["parts"][0]["text"]

            json_match = re.search(r"\{.*\}", text_response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                matched_asset_id = result.get("asset_id")
                if matched_asset_id == "UNKNOWN":
                    matched_asset_id = None
        except Exception as e:
            print(f"Gemini AI classification failed: {e}. Falling back to heuristics.")

    # FALLBACK: If AI didn't find anything (or failed), use our bulletproof keyword heuristics
    if not matched_asset_id:
        keywords_map = {
            "champions league": "ASSET-001",
            "uefa": "ASSET-001",
            "nba": "ASSET-002",
            "ipl": "ASSET-003",
            "cricket": "ASSET-003",
            "wimbledon": "ASSET-004",
            "tennis": "ASSET-004",
            "fifa": "ASSET-005",
            "world cup": "ASSET-005",
            "kabaddi": "ASSET-006",
            "pkl": "ASSET-006",
            "badminton": "ASSET-007",
            "bwf": "ASSET-007",
            "premier league": "ASSET-008",
            "epl": "ASSET-008",
            "la liga": "ASSET-009",
            "laliga": "ASSET-009",
            "bundesliga": "ASSET-010",
            "serie a": "ASSET-011",
            "seriea": "ASSET-011",
            "calcio": "ASSET-011",
            "ligue 1": "ASSET-012",
            "ligue1": "ASSET-012",
            "isl": "ASSET-013",
            "indian super league": "ASSET-013",
            "eredivisie": "ASSET-014",
            "a-league": "ASSET-015",
            "a league": "ASSET-015",
            "mls": "ASSET-016",
            "major league soccer": "ASSET-016",
        }

        for kw, asset_id in keywords_map.items():
            if kw in combined_text:
                matched_asset_id = asset_id
                break

    if matched_asset_id:
        assets = get_all_assets()
        for asset in assets:
            if asset.asset_id == matched_asset_id:
                return asset.canonical_fingerprint

    return None  # Will trigger 'unknown_asset' verdict
