import os
import time
from pathlib import Path
import matplotlib
# Use the 'Agg' backend so matplotlib can generate images without a GUI window
matplotlib.use('Agg')
import matplotlib.pyplot as plt

TMP_DIR = Path("data/tmp")

def create_data_chart(
    title: str, 
    labels: list[str], 
    values: list[float], 
    chart_type: str = "bar"
) -> str:
    """
    Generates a chart image based on provided data, saves it locally, and 
    returns the complete Markdown image syntax string.
    
    Use this tool whenever the user provides numerical data, tables, or asks for 
    a visual representation of statistics, growth, trends, or comparisons.

    Args:
        title (str): The main header/title displayed on the chart.
        labels (list[str]): The names for the data points (X-axis keys or pie slices).
        values (list[float]): The numerical metrics matching the order of labels.
        chart_type (str): The visual layout style. Must be 'bar', 'line', or 'pie'.

    Returns:
        str: The raw Markdown syntax snippet (e.g., '![Title](data/tmp/chart_171587.png)') 
             to be printed directly in the conversation response block.
    """
    # Ensure the target directory exists
    if not TMP_DIR.exists():
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        
    # Generate a unique filename internally using the current epoch timestamp
    unique_id = int(time.time())
    file_path = TMP_DIR / f"chart_{unique_id}.png"

    try:
        # Clear any existing plots to prevent data bleeding across tool calls
        plt.clf()
        plt.figure(figsize=(8, 5))
        
        # Plot data based on type requested by the LLM
        if chart_type.lower() == "bar":
            plt.bar(labels, values, color='#3b82f6') # Modern clean blue
            plt.ylabel("Values")
            plt.xticks(rotation=45, ha='right')
        elif chart_type.lower() == "line":
            plt.plot(labels, values, marker='o', color='#10b981', linewidth=2) # Clean green
            plt.grid(True, linestyle='--', alpha=0.6)
            plt.xticks(rotation=45, ha='right')
        elif chart_type.lower() == "pie":
            plt.pie(values, labels=labels, autopct='%1.1f%%', startangle=140, 
                    colors=['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'])
        else:
            return "Error: Unsupported chart_type. Please use 'bar', 'line', or 'pie'."

        plt.title(title, pad=20, fontsize=14, fontweight='bold')
        plt.tight_layout() # Prevents label clipping

        # Save the file
        plt.savefig(file_path, dpi=150)
        plt.close()

        # Return the clean markdown image string directly
        return f"![{title}]({file_path.as_posix()})"

    except Exception as e:
        plt.close()
        return f"Error: Failed to generate chart image due to: {str(e)}"
        