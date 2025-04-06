import os
import logging
import time
import requests
import asyncio
import aiohttp
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

class SmarketsAPI:
    """
    Client for the Smarkets API to retrieve betting markets and odds.

    Note: Smarkets API access requires approval from Smarkets.
    As of 2024, there were reports that Smarkets was not onboarding
    new API users. Verify the current status before implementation.
    """
    BASE_URL = "https://api.smarkets.com/v3"
    REQUEST_DELAY = 1.0  # seconds between requests

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._setup_logger()

        self.username = os.environ.get("SMARKETS_USERNAME")
        self.password = os.environ.get("SMARKETS_PASSWORD")
        self.app_key = os.environ.get("SMARKETS_APP_KEY")
        self.session_token = None
        self.last_login_time = None
        self.last_request_time = 0

        self.request_count = 0
        self.rate_limit_delays = 0
        self.auth_attempts = 0
        self.auth_failures = 0

        self.logger.info("Initialized Smarkets API client")

    def _setup_logger(self):
        """Set up dedicated logging for Smarkets API"""
        os.makedirs("logs", exist_ok=True)
        file_handler = logging.FileHandler("logs/smarkets.log")
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def _ensure_auth(self):
        """Check if session is valid, login if necessary"""
        if not self.session_token or not self.last_login_time or \
           (datetime.now() - self.last_login_time) > timedelta(hours=23):
            self._login()
        return self.session_token is not None

    def _login(self):
        """Authenticate with Smarkets API using token-based authentication"""
        self.auth_attempts += 1
        if not self.username or not self.password or not self.app_key:
            self.logger.error("Smarkets credentials not found in environment variables")
            self.auth_failures += 1
            return False

        try:
            login_url = f"{self.BASE_URL}/sessions/"
            payload = {"username": self.username, "password": self.password, "app_key": self.app_key}
            response = requests.post(login_url, json=payload)
            if response.status_code == 200:
                data = response.json()
                self.session_token = data.get("token")
                self.last_login_time = datetime.now()
                token_preview = self.session_token[:5] + "..." if self.session_token else "None"
                self.logger.info(f"Successfully authenticated with Smarkets API. Token: {token_preview}")
                return True
            else:
                self.auth_failures += 1
                self.logger.error(f"Failed to authenticate with Smarkets API: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            self.auth_failures += 1
            self.logger.error(f"Error during Smarkets authentication: {str(e)}")
            return False

    def _make_request(self, endpoint: str, method: str = "GET", params: Dict = None, data: Dict = None) -> Dict:
        """Make an authenticated request to the Smarkets API with rate limiting"""
        if not self._ensure_auth():
            self.logger.error("Authentication failed, cannot make request")
            return {"detail": "Authentication failed"}

        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < self.REQUEST_DELAY:
            sleep_time = self.REQUEST_DELAY - time_since_last_request
            self.logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
            self.rate_limit_delays += 1

        url = f"{self.BASE_URL}/{endpoint}"
        headers = {"Authorization": f"Token {self.session_token}"}
        self.request_count += 1

        try:
            self.last_request_time = time.time()
            self.logger.debug(f"Making {method} request to {endpoint}")
            if method == "GET":
                response = requests.get(url, headers=headers, params=params)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data)
            else:
                self.logger.error(f"Unsupported HTTP method: {method}")
                return {"detail": f"Unsupported HTTP method: {method}"}
            if response.status_code in (200, 201):
                self.logger.debug(f"Request to {endpoint} successful: {response.status_code}")
                return response.json()
            else:
                self.logger.error(f"API request failed: {response.status_code} - {response.text}")
                if response.status_code == 401:
                    self.logger.warning("Authentication error, attempting to refresh token")
                    self.session_token = None
                    if self._ensure_auth():
                        self.logger.info("Token refreshed, retrying request")
                        return self._make_request(endpoint, method, params, data)
                return {"detail": f"API request failed: {response.status_code} - {response.text}"}
        except Exception as e:
            self.logger.error(f"Error making request to Smarkets API: {str(e)}")
            return {"detail": f"Error making request to Smarkets API: {str(e)}"}

    def list_football_competitions(self) -> List[Dict[str, Any]]:
        """Get a list of football competitions available on Smarkets"""
        self.logger.info("Fetching football competitions from Smarkets")
        response = self._make_request("events/", params={"type_name": "competition", "sport_name": "football"})
        if "detail" in response:
            return []
        competitions = [{"competition_id": event.get("id"), "name": event.get("name"), "country": event.get("country_code", ""), "start_date": event.get("start_datetime")} for event in response.get("events", [])]
        self.logger.info(f"Found {len(competitions)} football competitions on Smarkets")
        return competitions

    def list_events_by_competition(self, competition_id: str) -> List[Dict[str, Any]]:
        """Get a list of upcoming events for a specific competition"""
        self.logger.info(f"Fetching events for competition {competition_id}")
        response = self._make_request(f"events/", params={"parent_id": competition_id, "state": "upcoming", "limit": 100})
        if "detail" in response:
            return []
        events = [{"event_id": event.get("id"), "name": event.get("name"), "start_time": event.get("start_datetime"), "status": event.get("state")} for event in response.get("events", [])]
        self.logger.info(f"Found {len(events)} events for competition {competition_id}")
        return events

    def list_markets_for_event(self, event_id: str) -> List[Dict[str, Any]]:
        """Get a list of markets for a specific event"""
        self.logger.info(f"Fetching markets for event {event_id}")
        response = self._make_request(f"events/{event_id}/markets")
        if "detail" in response:
            return []
        markets = [{"market_id": market.get("id"), "market_name": market.get("name"), "event_id": event_id, "type": market.get("type_name")} for market in response.get("markets", []) if market.get("type_name") in ("1x2", "winner")]
        self.logger.info(f"Found {len(markets)} markets for event {event_id}")
        return markets

    def get_market_odds(self, market_id: str) -> Dict[str, Any]:
        """Get the current odds for a specific market"""
        self.logger.info(f"Fetching odds for market {market_id}")
        if market_id.startswith("sm_") and not self._ensure_auth():
            self.logger.warning(f"Using fallback sample odds data for market {market_id}")
            return self._get_fallback_odds(market_id)
        try:
            response = self._make_request(f"markets/{market_id}/quotes")
            if "detail" in response:
                self.logger.warning(f"Failed to get odds from Smarkets API: {response['detail']}")
                return self._get_fallback_odds(market_id)
            contracts_response = self._make_request(f"markets/{market_id}/contracts")
            contracts = {contract.get("id"): contract.get("name") for contract in contracts_response.get("contracts", [])}
            runners = []
            for contract_id, quotes in response.get("quotes", {}).items():
                if contract_id in contracts:
                    back_prices = sorted([q for q in quotes if q.get("side") == "buy"], key=lambda x: x.get("price"), reverse=True)
                    lay_prices = sorted([q for q in quotes if q.get("side") == "sell"], key=lambda x: x.get("price"))
                    best_back_price = back_prices[0].get("price") / 100 if back_prices else None
                    best_lay_price = lay_prices[0].get("price") / 100 if lay_prices else None
                    runners.append({"selection_id": contract_id, "runner_name": contracts.get(contract_id, f"Unknown ({contract_id})"), "back_odds": best_back_price, "lay_odds": best_lay_price})
            self.logger.info(f"Fetched odds for {len(runners)} runners in market {market_id}")
            return {"market_id": market_id, "runners": runners}
        except Exception as e:
            self.logger.error(f"Error fetching odds from Smarkets API: {str(e)}")
            return self._get_fallback_odds(market_id)

    def _get_fallback_odds(self, market_id: str) -> Dict[str, Any]:
        """Provide fallback sample odds data when API access is not available"""
        self.logger.info(f"Using fallback sample odds data for market {market_id}")
        sample_runners = []
        if market_id == "sm_1234567":  # Arsenal vs Chelsea
            sample_runners = [{"selection_id": "sr_1", "runner_name": "Arsenal", "back_odds": 2.10, "lay_odds": 2.15}, {"selection_id": "sr_2", "runner_name": "Draw", "back_odds": 3.50, "lay_odds": 3.60}, {"selection_id": "sr_3", "runner_name": "Chelsea", "back_odds": 3.20, "lay_odds": 3.30}]
        elif market_id == "sm_1234568":  # Liverpool vs Manchester United
            sample_runners = [{"selection_id": "sr_4", "runner_name": "Liverpool", "back_odds": 1.65, "lay_odds": 1.70}, {"selection_id": "sr_5", "runner_name": "Draw", "back_odds": 3.90, "lay_odds": 4.00}, {"selection_id": "sr_6", "runner_name": "Manchester United", "back_odds": 4.80, "lay_odds": 5.00}]
        else:
            sample_runners = [{"selection_id": "sr_7", "runner_name": "Home Team", "back_odds": 2.20, "lay_odds": 2.30}, {"selection_id": "sr_8", "runner_name": "Draw", "back_odds": 3.40, "lay_odds": 3.50}, {"selection_id": "sr_9", "runner_name": "Away Team", "back_odds": 3.00, "lay_odds": 3.10}]
        import random
        for runner in sample_runners:
            variation = random.uniform(0.95, 1.05)
            runner["back_odds"] = round(runner["back_odds"] * variation, 2)
            runner["lay_odds"] = round(runner["lay_odds"] * variation, 2)
            runner["lay_odds"] = max(runner["lay_odds"], runner["back_odds"] + 0.01)
        return {"market_id": market_id, "runners": sample_runners}

    def list_live_markets(self, competition_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get a list of live football markets, optionally filtered by competition names"""
        self.logger.info("Fetching live football markets from Smarkets")
        if not self.username or not self.password or not self.app_key:
            self.logger.warning("Smarkets API credentials not set, using fallback sample data")
            return self._get_fallback_markets()
        if not self._ensure_auth():
            self.logger.warning("Smarkets authentication failed, using fallback sample data")
            return self._get_fallback_markets()
        try:
            competitions = self.list_football_competitions()
            if not competitions:
                self.logger.warning("No competitions retrieved from Smarkets API, using fallback sample data")
                return self._get_fallback_markets()
            if competition_filter:
                competitions = [c for c in competitions if any(filt.lower() in c["name"].lower() for filt in competition_filter)]
            all_markets = []
            for comp in competitions[:5]:
                events = self.list_events_by_competition(comp["competition_id"])
                for event in events[:10]:
                    markets = self.list_markets_for_event(event["event_id"])
                    for market in markets:
                        all_markets.append({"market_id": market["market_id"], "market_name": market["market_name"], "event_name": event["name"], "competition": comp["name"], "start_time": event["start_time"]})
                    time.sleep(self.REQUEST_DELAY)
            self.logger.info(f"Found {len(all_markets)} live markets on Smarkets")
            return all_markets
        except Exception as e:
            self.logger.error(f"Error fetching live markets from Smarkets: {str(e)}")
            self.logger.info("Using fallback sample data")
            return self._get_fallback_markets()

    async def async_list_live_markets(self, competition_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Asynchronously fetch live football markets from Smarkets API.

        Args:
            competition_filter: Optional list of competition names to filter by (exact match required)

        Returns:
            List of dictionaries containing market information:
            - market_id (str)
            - market_name (str)
            - event_name (str)
            - competition (str)
            - start_time (str)
            - runners (dict - mapping of selection_id to runner name)
        """
        self.logger.info("Fetching live football markets asynchronously from Smarkets")
        if not self._ensure_auth():
            self.logger.error("Authentication failed, cannot fetch live markets")
            return []

        try:
            async with aiohttp.ClientSession() as session:
                # Fetch football competitions
                comp_url = f"{self.BASE_URL}/events/"
                params = {"type_name": "competition", "sport_name": "football"}
                headers = {"Authorization": f"Token {self.session_token}"}
                async with session.get(comp_url, headers=headers, params=params) as response:
                    if response.status != 200:
                        self.logger.error(f"Failed to fetch competitions: {response.status}")
                        return []
                    comp_data = await response.json()
                competitions = [{"competition_id": event.get("id"), "name": event.get("name")} for event in comp_data.get("events", [])]

                # Filter competitions by exact match if provided
                if competition_filter:
                    competitions = [c for c in competitions if c["name"] in competition_filter]
                    if not competitions:
                        self.logger.warning(f"No competitions found matching filter: {competition_filter}")
                        return []

                # Fetch live events
                all_markets = []
                for comp in competitions[:5]:  # Limit to 5 competitions
                    await asyncio.sleep(self.REQUEST_DELAY)  # Respect rate limit
                    params = {"parent_id": comp["competition_id"], "state": "live", "limit": 100}
                    async with session.get(comp_url, headers=headers, params=params) as response:
                        if response.status != 200:
                            self.logger.error(f"Failed to fetch events for {comp['name']}: {response.status}")
                            continue
                        event_data = await response.json()
                    events = [{"event_id": event.get("id"), "name": event.get("name"), "start_time": event.get("start_datetime")} for event in event_data.get("events", [])]

                    # Fetch markets and runners
                    for event in events[:10]:  # Limit to 10 events per competition
                        await asyncio.sleep(self.REQUEST_DELAY)  # Respect rate limit
                        markets_url = f"{self.BASE_URL}/events/{event['event_id']}/markets/"
                        async with session.get(markets_url, headers=headers) as response:
                            if response.status != 200:
                                self.logger.error(f"Failed to fetch markets for event {event['event_id']}: {response.status}")
                                continue
                            market_data = await response.json()
                        markets = [m for m in market_data.get("markets", []) if m.get("type_name") in ("1x2", "winner")]

                        for market in markets:
                            await asyncio.sleep(self.REQUEST_DELAY)  # Respect rate limit
                            contracts_url = f"{self.BASE_URL}/markets/{market['id']}/contracts/"
                            async with session.get(contracts_url, headers=headers) as response:
                                if response.status != 200:
                                    self.logger.error(f"Failed to fetch contracts for market {market['id']}: {response.status}")
                                    continue
                                contract_data = await response.json()
                            runners = {contract["id"]: contract["name"] for contract in contract_data.get("contracts", [])}

                            all_markets.append({
                                "market_id": market["id"],
                                "market_name": market["name"],
                                "event_name": event["name"],
                                "competition": comp["name"],
                                "start_time": event["start_time"],
                                "runners": runners
                            })

                self.logger.info(f"Fetched {len(all_markets)} live football markets asynchronously")
                return all_markets

        except Exception as e:
            self.logger.error(f"Error fetching live markets asynchronously: {str(e)}")
            return []

    def _get_fallback_markets(self) -> List[Dict[str, Any]]:
        """Provide fallback sample market data when API access is not available"""
        self.logger.info("Using fallback sample market data for Smarkets")
        sample_markets = [
            {"market_id": "sm_1234567", "market_name": "Match Odds", "event_name": "Arsenal vs Chelsea", "competition": "Premier League", "start_time": (datetime.now() + timedelta(days=1)).isoformat()},
            {"market_id": "sm_1234568", "market_name": "Match Odds", "event_name": "Liverpool vs Manchester United", "competition": "Premier League", "start_time": (datetime.now() + timedelta(days=2)).isoformat()},
            {"market_id": "sm_1234569", "market_name": "Match Odds", "event_name": "Brighton vs West Ham", "competition": "Premier League", "start_time": (datetime.now() + timedelta(days=1)).isoformat()},
            {"market_id": "sm_1234570", "market_name": "Match Odds", "event_name": "Leeds vs Norwich", "competition": "Championship", "start_time": (datetime.now() + timedelta(days=1)).isoformat()},
            {"market_id": "sm_1234571", "market_name": "Match Odds", "event_name": "Sheffield United vs Burnley", "competition": "Championship", "start_time": (datetime.now() + timedelta(days=3)).isoformat()}
        ]
        return sample_markets

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    smarkets = SmarketsAPI()
    markets = smarkets.list_live_markets(["Premier League", "Championship"])
    print(f"Found {len(markets)} markets")
    if markets:
        sample_market = markets[0]
        print(f"Sample market: {sample_market['event_name']} - {sample_market['market_name']}")
        odds = smarkets.get_market_odds(sample_market["market_id"])
        print(f"Runners: {len(odds.get('runners', []))}")
        for runner in odds.get("runners", []):
            print(f"{runner['runner_name']}: Back: {runner['back_odds']}, Lay: {runner['lay_odds']}")
