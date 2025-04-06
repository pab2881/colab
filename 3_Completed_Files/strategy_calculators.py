import os
import logging
from typing import Dict, Any

class StrategyCalculators:
    """
    Class for calculating various betting strategies including arbitrage
    and lay-the-draw to identify profitable opportunities across betting exchanges.
    """
    
    # Default commission rates
    BETFAIR_COMMISSION = 0.05  # 5%
    SMARKETS_COMMISSION = 0.02  # 2%
    
    def __init__(self):
        """Initialize with logger setup"""
        self.logger = logging.getLogger(__name__)
        self._setup_logger()
    
    def _setup_logger(self):
        """Set up dedicated logging for strategy calculations"""
        os.makedirs("logs", exist_ok=True)
        file_handler = logging.FileHandler("logs/strategy.log")
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        # Only add handler if it doesn't already exist
        if not any(isinstance(h, logging.FileHandler) and h.baseFilename == file_handler.baseFilename 
                  for h in self.logger.handlers):
            self.logger.addHandler(file_handler)
    
    def calculate_arbitrage(self, back_odds: float, lay_odds: float, back_platform: str, stake: float) -> Dict[str, Any]:
        """
        Calculate potential arbitrage opportunities between back and lay bets.
        
        Args:
            back_odds: Decimal odds for the back bet (e.g., 2.0)
            lay_odds: Decimal odds for the lay bet (e.g., 2.1)
            back_platform: Either "betfair" or "smarkets"
            stake: GBP amount for the back bet (e.g., 100.0)
            
        Returns:
            Dictionary with profit, lay stake and profitability status
        """
        self.logger.info(f"Calculating arbitrage: back_odds={back_odds}, lay_odds={lay_odds}, back_platform={back_platform}, stake={stake}")
        
        # Input validation
        if back_odds < 1.0 or lay_odds < 1.0 or back_platform not in ["betfair", "smarkets"]:
            self.logger.error(f"Invalid input for arbitrage calculation: back_odds={back_odds}, lay_odds={lay_odds}, back_platform={back_platform}")
            return {"error": "Invalid input"}
        
        # Determine commissions based on platforms
        back_commission = self.BETFAIR_COMMISSION if back_platform == "betfair" else self.SMARKETS_COMMISSION
        lay_commission = self.SMARKETS_COMMISSION if back_platform == "betfair" else self.BETFAIR_COMMISSION
        
        # Calculate lay stake
        lay_stake = (back_odds * stake) / lay_odds
        
        # Calculate back profit
        back_profit = (back_odds - 1) * stake * (1 - back_commission)
        
        # Calculate potential profits
        # If back bet wins: back winnings minus lay liability
        profit_if_back_wins = back_profit - (lay_stake * (lay_odds - 1))
        
        # If lay bet wins: lay stake after commission minus back stake
        profit_if_lay_wins = lay_stake * (1 - lay_commission) - stake
        
        # Total profit is the minimum profit in either scenario
        profit = min(profit_if_back_wins, profit_if_lay_wins)
        is_profitable = profit > 0
        
        result = {
            "profit": round(profit, 2),
            "lay_stake": round(lay_stake, 2),
            "is_profitable": is_profitable
        }
        
        self.logger.info(f"Arbitrage result: profit={result['profit']}, lay_stake={result['lay_stake']}, is_profitable={result['is_profitable']}")
        return result
    
    def calculate_lay_the_draw(self, lay_odds: float, back_odds: float, lay_stake: float) -> Dict[str, Any]:
        """
        Calculate lay-the-draw strategy profitability.
        Lay the draw pre-match and back the draw in-play at improved odds.
        
        Args:
            lay_odds: Decimal odds to lay the draw (e.g., 3.5)
            back_odds: Decimal odds to back post-draw (e.g., 2.0)
            lay_stake: GBP amount to lay the draw (e.g., 50.0)
            
        Returns:
            Dictionary with profits in different scenarios and overall profitability status
        """
        self.logger.info(f"Calculating lay-the-draw: lay_odds={lay_odds}, back_odds={back_odds}, lay_stake={lay_stake}")
        
        # Input validation
        if lay_odds < 1.0 or back_odds < 1.0 or lay_stake <= 0:
            self.logger.error(f"Invalid input for lay-the-draw calculation: lay_odds={lay_odds}, back_odds={back_odds}, lay_stake={lay_stake}")
            return {"error": "Invalid input"}
        
        # Use Betfair commission for lay-the-draw calculations
        commission = self.BETFAIR_COMMISSION
        
        # Calculate liability
        liability = lay_stake * (lay_odds - 1)
        
        # Calculate profit if draw happens
        profit_if_draw = lay_stake * (1 - commission) - liability
        
        # Calculate profit if not a draw - lay wins and then we back
        profit_if_not_draw = lay_stake * (1 - commission) + (back_odds - 1) * lay_stake * (1 - commission)
        
        result = {
            "profit_if_draw": round(profit_if_draw, 2),
            "profit_if_not_draw": round(profit_if_not_draw, 2),
            "is_profitable": profit_if_not_draw > 0
        }
        
        self.logger.info(f"Lay-the-draw result: profit_if_draw={result['profit_if_draw']}, profit_if_not_draw={result['profit_if_not_draw']}, is_profitable={result['is_profitable']}")
        return result


# For testing or demonstration purposes
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    calculator = StrategyCalculators()
    
    # Test arbitrage calculation
    arb_result = calculator.calculate_arbitrage(2.0, 1.95, "betfair", 100.0)
    print(f"Arbitrage result: {arb_result}")
    
    # Test lay-the-draw calculation
    ltd_result = calculator.calculate_lay_the_draw(3.5, 2.0, 50.0)
    print(f"Lay-the-draw result: {ltd_result}")
