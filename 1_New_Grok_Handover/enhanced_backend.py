import os
import logging
import asyncio
import time
import json
import schedule
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uvicorn
from datetime import datetime

# Import our custom modules
from betfair_api import BetfairAPI
from smarkets_api import SmarketsAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/backend.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize APIs
betfair = BetfairAPI()
smarkets = SmarketsAPI()

# British competitions to focus on
BRITISH_COMPETITIONS = [
    "Premier League",
    "Championship",
    "League One",
    "League Two",
    "FA Cup",
    "EFL Cup",
    "Scottish Premiership",
    "Scottish Championship"
]

# Initialize FastAPI app
app = FastAPI(
    title="Heage Betting App API",
    description="API for fetching and analyzing betting opportunities across Betfair and Smarkets"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Pydantic models for request/response
class OddsData(BaseModel):
    market_id: str
    runners: List[Dict[str, Any]]

# Global variables to store the latest fetched data
live_markets_data = {
    "betfair": [],
    "smarkets": [],
    "last_updated": None,
    "is_fetching": False
}

async def fetch_and_store_markets():
    """
    Fetch data from Betfair and Smarkets APIs in parallel and store it,
    measuring lag between fetches
    """
    global live_markets_data

    if live_markets_data["is_fetching"]:
        logger.info("Skipping fetch as previous fetch is still in progress")
        return

    live_markets_data["is_fetching"] = True
    logger.info("Starting synchronized fetch of Betfair and Smarkets markets")
    start_time = time.time()

    # Create tasks for parallel fetching
    betfair_task = asyncio.create_task(betfair.async_list_live_markets(competition_filter=BRITISH_COMPETITIONS))
    smarkets_task = asyncio.create_task(smarkets.async_list_live_markets(competition_filter=BRITISH_COMPETITIONS))

    betfair_markets, smarkets_markets = None, None
    betfair_time, smarkets_time = 0, 0

    # Fetch Betfair markets with independent error handling
    try:
        betfair_start = time.time()
        betfair_markets = await betfair_task
        betfair_time = time.time() - betfair_start
        logger.info(f"Fetched {len(betfair_markets)} Betfair markets in {betfair_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Betfair fetch failed: {str(e)}")
        betfair_markets = []

    # Fetch Smarkets markets with independent error handling
    try:
        smarkets_start = time.time()
        smarkets_markets = await smarkets_task
        smarkets_time = time.time() - smarkets_start
        logger.info(f"Fetched {len(smarkets_markets)} Smarkets markets in {smarkets_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Smarkets fetch failed: {str(e)}")
        smarkets_markets = []

    # Calculate total fetch time and lag before file operations
    total_fetch_time = time.time() - start_time
    lag = abs(betfair_time - smarkets_time)

    if lag > 1.0:
        logger.warning(f"Fetch lag detected: {lag:.2f} seconds between Betfair and Smarkets")

    # Update data only if at least one fetch succeeded
    if betfair_markets or smarkets_markets:
        live_markets_data["betfair"] = betfair_markets or live_markets_data.get("betfair", [])
        live_markets_data["smarkets"] = smarkets_markets or live_markets_data.get("smarkets", [])
        live_markets_data["last_updated"] = datetime.now().isoformat()

        # Save to JSON file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        data_dir = "data"
        os.makedirs(data_dir, exist_ok=True)

        file_path = f"{data_dir}/markets_{timestamp}.json"
        with open(file_path, "w") as f:
            json.dump({
                "betfair": betfair_markets,
                "smarkets": smarkets_markets,
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "betfair_fetch_time": betfair_time,
                    "smarkets_fetch_time": smarkets_time,
                    "total_fetch_time": total_fetch_time,
                    "lag": lag
                }
            }, f, indent=2)

        logger.info(f"Saved market data to {file_path}")
    else:
        logger.error("Both Betfair and Smarkets fetches failed, no data updated")

    live_markets_data["is_fetching"] = False

def schedule_market_fetching():
    """Set up scheduled fetching every 5 minutes"""
    schedule.every(5).minutes.do(lambda: asyncio.create_task(fetch_and_store_markets()))
    logger.info("Scheduled market fetching every 5 minutes")

@app.on_event("startup")
async def startup_event():
    """Initialize data and start scheduled tasks on startup"""
    logger.info("Starting up backend server")
    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True)

    # Initial fetch on startup as a non-blocking background task
    asyncio.create_task(fetch_and_store_markets())

    # Set up scheduled fetching
    schedule_market_fetching()

    # Start the scheduler in a background task
    asyncio.create_task(run_scheduler())

async def run_scheduler():
    """Run the scheduler in the background"""
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    return {
        "status": "healthy",
        "message": "Heage Betting App API is running",
        "endpoints": [
            "/health",
            "/api/live-markets",
            "/api/odds/{platform}/{market_id}"
        ]
    }

@app.get("/health")
async def health_check():
    logger.info("Health check endpoint accessed")

    try:
        # Check if we have any data and when it was last updated
        last_updated = live_markets_data.get("last_updated")
        has_data = len(live_markets_data.get("betfair", [])) > 0 or len(live_markets_data.get("smarkets", [])) > 0

        # Check platform APIs
        betfair_connected = betfair.check_connection() if hasattr(betfair, 'check_connection') else False
        smarkets_connected = smarkets.test_connection() if hasattr(smarkets, 'test_connection') else False

        return {
            "status": "healthy" if (betfair_connected or smarkets_connected) and has_data else "degraded",
            "betfair_status": "connected" if betfair_connected else "disconnected",
            "smarkets_status": "connected" if smarkets_connected else "disconnected",
            "has_data": has_data,
            "last_updated": last_updated,
            "is_fetching": live_markets_data["is_fetching"],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in health check: {str(e)}")
        # Return healthy anyway to prevent frontend failures
        return {
            "status": "degraded",
            "message": f"Error checking API health: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

@app.get("/api/live-markets")
async def get_live_markets(
    platform: Optional[str] = Query(None, description="Filter by platform: betfair, smarkets, or all"),
    competition: Optional[str] = Query(None, description="Filter by competition name")
):
    logger.info(f"Received request for live markets with platform={platform}, competition={competition}")

    try:
        # If no platform specified or "all", return both
        platforms_to_return = []
        if platform is None or platform.lower() == "all":
            platforms_to_return = ["betfair", "smarkets"]
        elif platform.lower() in ["betfair", "smarkets"]:
            platforms_to_return = [platform.lower()]
        else:
            raise HTTPException(status_code=400, detail=f"Invalid platform: {platform}. Must be 'betfair', 'smarkets', or 'all'")

        result = {}
        for plat in platforms_to_return:
            markets = live_markets_data.get(plat, [])

            # Apply competition filter if specified
            if competition:
                markets = [market for market in markets if competition.lower() in market.get("competition", "").lower()]

            result[plat] = markets

        result["last_updated"] = live_markets_data.get("last_updated")
        result["is_fetching"] = live_markets_data.get("is_fetching", False)

        logger.info(f"Returning {sum(len(result[plat]) for plat in platforms_to_return)} markets to client")
        return result

    except Exception as e:
        logger.error(f"Error processing live markets request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/api/odds/{platform}/{market_id}")
async def get_market_odds(
    platform: str,
    market_id: str
):
    logger.info(f"Received request for {platform} odds for market {market_id}")

    try:
        if platform.lower() == "betfair":
            odds = betfair.get_market_odds(market_id)
        elif platform.lower() == "smarkets":
            odds = smarkets.get_market_odds(market_id)
        else:
            raise HTTPException(status_code=400, detail=f"Invalid platform: {platform}. Must be 'betfair' or 'smarkets'")

        if not odds or "detail" in odds:
            error_msg = odds.get("detail") if isinstance(odds, dict) and "detail" in odds else "Failed to get odds"
            logger.error(f"Failed to fetch {platform} odds for market {market_id}: {error_msg}")
            raise HTTPException(status_code=404, detail=f"No odds found for market {market_id} on {platform}")

        return odds

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching {platform} odds for market {market_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Run the server
if __name__ == "__main__":
    logger.info("Starting Enhanced Backend on port 3003")
    uvicorn.run("enhanced_backend:app", host="0.0.0.0", port=3003, reload=True)
