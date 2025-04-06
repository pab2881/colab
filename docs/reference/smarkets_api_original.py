import os
import logging
import time
import requests
from typing import Dict, List, Any, Optional

class SmarketsAPI:
    """Basic client for Smarkets API to retrieve betting markets and odds."""
    BASE_URL = "https://api.smarkets.com/v3"
    REQUEST_DELAY = 1.0  # seconds between requests

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._setup_logger()
        self.username = os.environ.get("SMARKETS_USERNAME")
        self.password = os.environ.get("SMARKETS_PASSWORD")
        self.app_key = os.environ.get("SMARKETS_APP_KEY")
        self.session_token = None
        self.last_request_time = 0

    def _setup_logger(self):
        """Set up logging to smarkets.log."""
        os.makedirs("logs", exist_ok=True)
        handler = logging.FileHandler("logs/smarkets.log")
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def _login(self):
        """Authenticate with Smarkets API."""
        if not all([self.username, self.password, self.app_key]):
            self.logger.error("Missing Smarkets credentials")
            return False
        try:
            response = requests.post(
                f"{self.BASE_URL}/sessions/",
                json={"username": self.username, "password": self.password, "app_key": self.app_key}
            )
            if response.status_code == 200:
                self.session_token = response.json().get("token")
                self.logger.info("Logged into Smarkets API")
                return True
            self.logger.error(f"Login failed: {response.text}")
            return False
        except Exception as e:
            self.logger.error(f"Login error: {str(e)}")
            return False

    def _make_request(self, endpoint: str, params: Dict = None) -> Dict:
        """Make an authenticated GET request."""
        if not self.session_token and not self._login():
            return {"detail": "Authentication failed"}
        time.sleep(self.REQUEST_DELAY)  # Basic rate limiting
        headers = {"Authorization": f"Token {self.session_token}"}
        try:
            response = requests.get(f"{self.BASE_URL}/{endpoint}", headers=headers, params=params)
            if response.status_code == 200:
                return response.json()
            self.logger.error(f"Request failed: {response.text}")
            return {"detail": f"Error: {response.status_code}"}
        except Exception as e:
            self.logger.error(f"Request error: {str(e)}")
            return {"detail": str(e)}

    def list_live_markets(self, competition_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Fetch live football markets (synchronous)."""
        self.logger.info("Fetching live markets")
        competitions = self._make_request("events/", params={"type_name": "competition", "sport_name": "football"})
        if "detail" in competitions:
            return []
        comp_list = [{"id": c.get("id"), "name": c.get("name")} for c in competitions.get("events", [])]
        if competition_filter:
            comp_list = [c for c in comp_list if c["name"] in competition_filter]

        markets = []
        for comp in comp_list[:5]:  # Limit to 5 competitions
            events = self._make_request("events/", params={"parent_id": comp["id"], "state": "live"})
            if "detail" in events:
                continue
            for event in events.get("events", [])[:10]:  # Limit to 10 events
                market_data = self._make_request(f"events/{event['id']}/markets/")
                if "detail" in market_data:
                    continue
                for market in market_data.get("markets", []):
                    markets.append({
                        "market_id": market["id"],
                        "market_name": market["name"],
                        "event_name": event["name"],
                        "competition": comp["name"],
                        "start_time": event["start_datetime"]
                    })
        self.logger.info(f"Fetched {len(markets)} live markets")
        return markets

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    api = SmarketsAPI()
    markets = api.list_live_markets(["Premier League"])
    print(f"Found {len(markets)} markets")
