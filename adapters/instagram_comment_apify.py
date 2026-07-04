import asyncio
import os
import httpx
from typing import Any

from adapters.base import BaseAdapter
from schemas.common import ToolResult

class InstagramCommentApifyAdapter(BaseAdapter):
    """Adapter to fetch Instagram comments using Apify."""
    
    name: str = "instagram_comment_apify"
    default_timeout: float = 300.0  # Apify actors can take some time

    async def _execute(self, query: str) -> ToolResult:
        """Execute the Apify actor for a given Instagram URL (query)."""
        api_key = os.getenv("APIFY_API_KEY")
        if not api_key:
            return ToolResult(tool=self.name, success=False, error="APIFY_API_KEY is not set.")
            
        actor_id = "apify/instagram-comment-scraper"
        
        run_url = f"https://api.apify.com/v2/acts/{actor_id}/runs?token={api_key}"
        payload = {
            "directUrls": [query],
            "resultsLimit": 200,
        }
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                # 1. Start the Actor
                await self._emit_progress({"status": "starting apify actor", "url": query})
                run_res = await client.post(run_url, json=payload)
                run_res.raise_for_status()
                run_data = run_res.json()["data"]
                run_id = run_data["id"]
                default_dataset_id = run_data["defaultDatasetId"]
                
                # 2. Poll for completion
                status_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={api_key}"
                while True:
                    status_res = await client.get(status_url)
                    status_res.raise_for_status()
                    current_status = status_res.json()["data"]["status"]
                    if current_status in ["SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"]:
                        if current_status != "SUCCEEDED":
                            return ToolResult(tool=self.name, success=False, error=f"Apify run ended with status {current_status}")
                        break
                    await asyncio.sleep(5)
                
                # 3. Fetch results
                await self._emit_progress({"status": "fetching dataset", "dataset_id": default_dataset_id})
                dataset_url = f"https://api.apify.com/v2/datasets/{default_dataset_id}/items?token={api_key}"
                data_res = await client.get(dataset_url)
                data_res.raise_for_status()
                items = data_res.json()
                
                # 4. Normalize results
                normalized_comments = []
                for item in items:
                    normalized_comments.append({
                        "id": item.get("id"),
                        "text": item.get("text"),
                        "timestamp": item.get("timestamp"),
                        "likesCount": item.get("likesCount", 0),
                        "repliesCount": item.get("repliesCount", 0),
                        "ownerUsername": item.get("ownerUsername"),
                        "ownerId": item.get("ownerId"),
                        "ownerProfilePicUrl": item.get("ownerProfilePicUrl"),
                        "postUrl": query,
                        "platform": "Instagram",
                        "evidence_source": "Apify"
                    })
                
                return ToolResult(
                    tool=self.name,
                    success=True,
                    data=normalized_comments
                )
                
            except Exception as e:
                return ToolResult(tool=self.name, success=False, error=str(e))
