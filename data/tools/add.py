from typing import Union

def add(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    Add two numbers together.
    
    This function takes two numbers (integers or floats) and returns their sum.
    
    Args:
        a (Union[int, float]): First number to add
        b (Union[int, float]): Second number to add
        
    Returns:
        Union[int, float]: The sum of a and b
    """
    return a + b
