import numpy as np
from collections import deque

class VolatilityPredictor:
    """
    Calculates historical volatility using the standard deviation of returns.
    """
    def __init__(self, period=20):
        """
        Initializes the VolatilityPredictor.

        Args:
            period (int): The number of recent prices to use for the calculation.
        """
        self.period = period
        self.prices = deque(maxlen=period)

    def update(self, price):
        """
        Updates the predictor with a new price.

        Args:
            price (float): The latest price.
        """
        self.prices.append(price)

    def get_volatility(self):
        """
        Calculates the volatility.

        Returns:
            float: The standard deviation of the simple returns, or 0.0 if there is not enough data.
        """
        if len(self.prices) < 2:
            return 0.0

        prices_arr = np.array(list(self.prices))
        returns = np.diff(prices_arr) / prices_arr[:-1]

        return np.std(returns)
