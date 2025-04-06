import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class HedgeOpportunity:
    """Class representing a cross-platform hedge opportunity"""
    event_name: str
    runner_name: str
    back_exchange: str
    lay_exchange: str
    back_odds: float
    lay_odds: float
    stake: float
    lay_stake: float
    profit: float
    profit_percentage: float
    back_market_id: str
    lay_market_id: str
    back_selection_id: str
    lay_selection_id: str
    back_commission: float
    lay_commission: float
    back_platform: str = ""
    lay_platform: str = ""

class HedgeCalculator:
    """
    Enhanced calculator for hedge betting opportunities across Betfair, Smarkets and traditional bookmakers
    """
    
    # Default commission rates
    BETFAIR_COMMISSION = 0.05  # 5%
    SMARKETS_COMMISSION = 0.02  # 2%
    ODDS_API_MARGIN = 0.0  # Traditional bookmakers don't charge explicit commission
    
    def __init__(self, betfair_commission: float = BETFAIR_COMMISSION, 
                smarkets_commission: float = SMARKETS_COMMISSION,
                odds_api_margin: float = ODDS_API_MARGIN):
        self.logger = logging.getLogger(__name__)
        self.betfair_commission = betfair_commission
        self.smarkets_commission = smarkets_commission
        self.odds_api_margin = odds_api_margin
    
    def calculate_hedge(self, back_odds: float, lay_odds: float, 
                        stake: float = 100.0,
                        back_commission: float = 0.0,
                        lay_commission: float = 0.0) -> Optional[Dict[str, float]]:
        """
        Calculate the hedge bet and potential profit
        
        Args:
            back_odds: Back odds (e.g., 2.0)
            lay_odds: Lay odds (e.g., 1.95)
            stake: Initial stake amount for back bet
            back_commission: Commission rate for back exchange (e.g., 0.05 for 5%)
            lay_commission: Commission rate for lay exchange (e.g., 0.02 for 2%)
            
        Returns:
            Dictionary with hedge calculations or None if not profitable
        """
        if not back_odds or not lay_odds or back_odds <= 0 or lay_odds <= 0 or lay_odds <= 1:
            return None
        
        # Calculate potential winnings from back bet (after commission)
        back_winnings = stake * (back_odds - 1) * (1 - back_commission)
        
        # Calculate lay stake required to hedge
        lay_stake = (stake * back_odds) / lay_odds
        
        # Calculate lay liability
        lay_liability = lay_stake * (lay_odds - 1)
        
        # Calculate profit scenarios
        # If back bet wins: back winnings minus lay liability
        profit_if_back_wins = back_winnings - lay_liability
        
        # If lay bet wins: lay winnings (after commission) minus initial stake
        profit_if_lay_wins = lay_stake * (1 - lay_commission) - stake
        
        # The guaranteed profit is the minimum of the two scenarios
        profit = min(profit_if_back_wins, profit_if_lay_wins)
        profit_percentage = (profit / stake) * 100
        
        return {
                        "lay_stake": round(lay_stake, 2),
            "lay_liability": round(lay_liability, 2),
            "profit_if_back_wins": round(profit_if_back_wins, 2),
            "profit_if_lay_wins": round(profit_if_lay_wins, 2),
            "profit": round(profit, 2),
            "profit_percentage": round(profit_percentage, 2)
        }
    
    def calculate_bookmaker_hedge(self, bookmaker_odds: float, exchange_lay_odds: float,
                                stake: float = 100.0, exchange_commission: float = 0.05) -> Optional[Dict[str, float]]:
        """
        Calculate hedge between a traditional bookmaker (back) and an exchange (lay)
        
        Args:
            bookmaker_odds: Bookmaker back odds
            exchange_lay_odds: Exchange lay odds
            stake: Stake amount for bookmaker bet
            exchange_commission: Commission rate for the exchange
            
        Returns:
            Dictionary with hedge calculations or None if not profitable
        """
        return self.calculate_hedge(bookmaker_odds, exchange_lay_odds, stake, 0.0, exchange_commission)
    
    def find_odds_api_exchange_opportunities(self,
                                          odds_api_market_id: str,
                                          exchange_market_id: str,
                                          exchange_platform: str,  # 'betfair' or 'smarkets'
                                          odds_api_odds: Dict[str, Any],
                                          exchange_odds: Dict[str, Any],
                                          runner_matches: Dict[str, str],
                                          event_info: Dict[str, Any],
                                          stake: float = 100.0) -> List[HedgeOpportunity]:
        """
        Find hedge opportunities between a traditional bookmaker and an exchange
        
        Args:
            odds_api_market_id: The Odds API market ID
            exchange_market_id: Exchange market ID (Betfair or Smarkets)
            exchange_platform: Which exchange ('betfair' or 'smarkets')
            odds_api_odds: Odds data from The Odds API
            exchange_odds: Odds data from the exchange
            runner_matches: Dictionary mapping The Odds API selection IDs to exchange selection IDs
            event_info: Information about the event (name, competition, etc.)
            stake: Initial stake amount
            
        Returns:
            List of hedge opportunities sorted by profit
        """
        opportunities = []
        
        # Determine exchange commission
        exchange_commission = self.betfair_commission if exchange_platform == 'betfair' else self.smarkets_commission
        
        # Create lookup dictionaries for runners by selection ID
        odds_api_runners = {runner.get("selection_id"): runner for runner in odds_api_odds.get("runners", [])}
        exchange_runners = {runner.get("selection_id"): runner for runner in exchange_odds.get("runners", [])}
        
        # Check bookmaker back vs exchange lay
        for odds_api_selection_id, exchange_selection_id in runner_matches.items():
            odds_api_runner = odds_api_runners.get(odds_api_selection_id)
            exchange_runner = exchange_runners.get(exchange_selection_id)
            
            if not odds_api_runner or not exchange_runner:
                continue
                
            bookmaker_odds = odds_api_runner.get("back_odds")
            exchange_lay_odds = exchange_runner.get("best_lay_price")
            
            if bookmaker_odds and exchange_lay_odds and bookmaker_odds > 0 and exchange_lay_odds > 0:
                hedge_result = self.calculate_bookmaker_hedge(
                    bookmaker_odds, 
                    exchange_lay_odds, 
                    stake, 
                    exchange_commission
                )
                
                if hedge_result and hedge_result["profit"] > 0:
                    opportunities.append(HedgeOpportunity(
                        event_name=event_info.get("event_name", "Unknown Event"),
                        runner_name=odds_api_runner.get("runner_name", "Unknown Runner"),
                        back_exchange=odds_api_odds.get("bookmaker", "Bookmaker"),
                        lay_exchange=exchange_platform.capitalize(),
                        back_odds=bookmaker_odds,
                        lay_odds=exchange_lay_odds,
                        stake=stake,
                        lay_stake=hedge_result["lay_stake"],
                        profit=hedge_result["profit"],
                        profit_percentage=hedge_result["profit_percentage"],
                        back_market_id=odds_api_market_id,
                        lay_market_id=exchange_market_id,
                        back_selection_id=odds_api_selection_id,
                        lay_selection_id=exchange_selection_id,
                        back_commission=0.0,
                        lay_commission=exchange_commission,
                        back_platform="oddsapi",
                        lay_platform=exchange_platform
                    ))
        
        # Sort opportunities by profit (descending)
        return sorted(opportunities, key=lambda x: x.profit, reverse=True)

    def find_all_cross_platform_opportunities(self, 
                                            matched_markets: List[Dict[str, Any]],
                                            odds_data: Dict[str, Dict[str, Dict[str, Any]]],
                                            runner_matches: Dict[str, Dict[str, Dict[str, str]]],
                                            min_profit_percentage: float = 0.5,
                                            stake: float = 100.0) -> List[HedgeOpportunity]:
        """
        Find all hedge opportunities across multiple platforms including traditional bookmakers
        
        Args:
            matched_markets: List of matched markets across platforms
            odds_data: Dictionary mapping platform and market IDs to odds data
            runner_matches: Dictionary mapping market pairs to runner match dictionaries
            min_profit_percentage: Minimum profit percentage to include
            stake: Initial stake amount
            
        Returns:
            List of hedge opportunities sorted by profit
        """
        all_opportunities = []
        
        for market in matched_markets:
            # We now have three possible platform combinations:
            # 1. Betfair vs Smarkets (original)
            # 2. Bookmaker vs Betfair
            # 3. Bookmaker vs Smarkets
            
            # Process 1: Betfair vs Smarkets (from original implementation)
            if 'betfair_market_id' in market and 'smarkets_market_id' in market:
                betfair_market_id = market.get("betfair_market_id")
                smarkets_market_id = market.get("smarkets_market_id")
                
                betfair_odds = odds_data.get('betfair', {}).get(betfair_market_id)
                smarkets_odds = odds_data.get('smarkets', {}).get(smarkets_market_id)
                
                bf_sm_matches = runner_matches.get(f'betfair_smarkets_{betfair_market_id}', {})
                
                if betfair_odds and smarkets_odds and bf_sm_matches:
                    # Process with original method - existing function from the base class
                    opportunities = self.find_cross_platform_opportunities(
                        betfair_market_id,
                        smarkets_market_id,
                        betfair_odds,
                        smarkets_odds,
                        bf_sm_matches,
                        market,
                        stake
                    )
                    
                    # Filter by minimum profit percentage
                    opportunities = [op for op in opportunities if op.profit_percentage >= min_profit_percentage]
                    all_opportunities.extend(opportunities)
            
            # Process 2: Bookmaker vs Betfair
            if 'oddsapi_market_id' in market and 'betfair_market_id' in market:
                oddsapi_market_id = market.get("oddsapi_market_id")
                betfair_market_id = market.get("betfair_market_id")
                
                oddsapi_odds = odds_data.get('oddsapi', {}).get(oddsapi_market_id)
                betfair_odds = odds_data.get('betfair', {}).get(betfair_market_id)
                
                oa_bf_matches = runner_matches.get(f'oddsapi_betfair_{oddsapi_market_id}', {})
                
                if oddsapi_odds and betfair_odds and oa_bf_matches:
                    opportunities = self.find_odds_api_exchange_opportunities(
                        oddsapi_market_id,
                        betfair_market_id,
                        'betfair',
                        oddsapi_odds,
                        betfair_odds,
                        oa_bf_matches,
                        market,
                        stake
                    )
                    
                    # Filter by minimum profit percentage
                    opportunities = [op for op in opportunities if op.profit_percentage >= min_profit_percentage]
                    all_opportunities.extend(opportunities)
            
            # Process 3: Bookmaker vs Smarkets
            if 'oddsapi_market_id' in market and 'smarkets_market_id' in market:
                oddsapi_market_id = market.get("oddsapi_market_id")
                smarkets_market_id = market.get("smarkets_market_id")
                
                oddsapi_odds = odds_data.get('oddsapi', {}).get(oddsapi_market_id)
                smarkets_odds = odds_data.get('smarkets', {}).get(smarkets_market_id)
                
                oa_sm_matches = runner_matches.get(f'oddsapi_smarkets_{oddsapi_market_id}', {})
                
                if oddsapi_odds and smarkets_odds and oa_sm_matches:
                    opportunities = self.find_odds_api_exchange_opportunities(
                        oddsapi_market_id,
                        smarkets_market_id,
                        'smarkets',
                        oddsapi_odds,
                        smarkets_odds,
                        oa_sm_matches,
                        market,
                        stake
                    )
                    
                    # Filter by minimum profit percentage
                    opportunities = [op for op in opportunities if op.profit_percentage >= min_profit_percentage]
                    all_opportunities.extend(opportunities)
        
        # Sort all opportunities by profit percentage (descending)
        return sorted(all_opportunities, key=lambda x: x.profit_percentage, reverse=True)
    
    def find_cross_platform_opportunities(self, 
                                        betfair_market_id: str,
                                        smarkets_market_id: str,
                                        betfair_odds: Dict[str, Any],
                                        smarkets_odds: Dict[str, Any],
                                        runner_matches: Dict[str, str],
                                        event_info: Dict[str, Any],
                                        stake: float = 100.0) -> List[HedgeOpportunity]:
        """
        Find hedge opportunities between Betfair and Smarkets for a matched market
        
        Args:
            betfair_market_id: Betfair market ID
            smarkets_market_id: Smarkets market ID
            betfair_odds: Odds data from Betfair
            smarkets_odds: Odds data from Smarkets
            runner 🙂matches: Dictionary mapping Betfair selection IDs to Smarkets selection IDs
            event_info: Information about the event (name, competition, etc.)
            stake: Initial stake amount
            
        Returns:
            List of hedge opportunities sorted by profit
        """
        opportunities = []
        
        # Create lookup dictionaries for runners by selection ID
        betfair_runners = {runner.get("selection_id"): runner for runner in betfair_odds.get("runners", [])}
        smarkets_runners = {runner.get("selection_id"): runner for runner in smarkets_odds.get("runners", [])}
        
        # Check Betfair back vs Smarkets lay
        for bf_selection_id, sm_selection_id in runner_matches.items():
            bf_runner = betfair_runners.get(bf_selection_id)
            sm_runner = smarkets_runners.get(sm_selection_id)
            
            if not bf_runner or not sm_runner:
                continue
                
            bf_back_odds = bf_runner.get("best_back_price")
            sm_lay_odds = sm_runner.get("best_lay_price")
            
            if bf_back_odds and sm_lay_odds and bf_back_odds > 0 and sm_lay_odds > 0:
                hedge_result = self.calculate_hedge(
                    bf_back_odds, 
                    sm_lay_odds, 
                    stake, 
                    self.betfair_commission, 
                    self.smarkets_commission
                )
                
                if hedge_result and hedge_result["profit"] > 0:
                    opportunities.append(HedgeOpportunity(
                        event_name=event_info.get("event_name", "Unknown Event"),
                        runner_name=bf_runner.get("runner_name", "Unknown Runner"),
                        back_exchange="Betfair",
                        lay_exchange="Smarkets",
                        back_odds=bf_back_odds,
                        lay_odds=sm_lay_odds,
                        stake=stake,
                        lay_stake=hedge_result["lay_stake"],
                        profit=hedge_result["profit"],
                        profit_percentage=hedge_result["profit_percentage"],
                        back_market_id=betfair_market_id,
                        lay_market_id=smarkets_market_id,
                        back_selection_id=bf_selection_id,
                        lay_selection_id=sm_selection_id,
                        back_commission=self.betfair_commission,
                        lay_commission=self.smarkets_commission,
                        back_platform="betfair",
                        lay_platform="smarkets"
                    ))
        
        # Check Smarkets back vs Betfair lay
        for bf_selection_id, sm_selection_id in runner_matches.items():
            bf_runner = betfair_runners.get(bf_selection_id)
            sm_runner = smarkets_runners.get(sm_selection_id)
            
            if not bf_runner or not sm_runner:
                continue
                
            sm_back_odds = sm_runner.get("best_back_price")
            bf_lay_odds = bf_runner.get("best_lay_price")
            
            if sm_back_odds and bf_lay_odds and sm_back_odds > 0 and bf_lay_odds > 0:
                hedge_result = self.calculate_hedge(
                    sm_back_odds, 
                    bf_lay_odds, 
                    stake, 
                    self.smarkets_commission, 
                    self.betfair_commission
                )
                
                if hedge_result and hedge_result["profit"] > 0:
                    opportunities.append(HedgeOpportunity(
                        event_name=event_info.get("event_name", "Unknown Event"),
                        runner_name=sm_runner.get("runner_name", "Unknown Runner"),
                        back_exchange="Smarkets",
                        lay_exchange="Betfair",
                        back_odds=sm_back_odds,
                        lay_odds=bf_lay_odds,
                        stake=stake,
                        lay_stake=hedge_result["lay_stake"],
                        profit=hedge_result["profit"],
                        profit_percentage=hedge_result["profit_percentage"],
                        back_market_id=smarkets_market_id,
                        lay_market_id=betfair_market_id,
                        back_selection_id=sm_selection_id,
                        lay_selection_id=bf_selection_id,
                        back_commission=self.smarkets_commission,
                        lay_commission=self.betfair_commission,
                        back_platform="smarkets",
                        lay_platform="betfair"
                    ))
        
        # Sort opportunities by profit (descending)
        return sorted(opportunities, key=lambda x: x.profit, reverse=True)

# Optionally, add a main block for testing or demonstration
if __name__ == "__main__":
    # Example usage and testing can be added here
    hedge_calculator = HedgeCalculator()
    print("Hedge Calculator initialized successfully.")
