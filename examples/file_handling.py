"""
CellCog SDK File Handling Example

This example demonstrates how to send files to CellCog and receive
generated files at specific locations.
"""

from cellcog import CellCogClient


def main():
    client = CellCogClient()

    # Example 1: Send a local file for analysis
    print("Example 1: Analyzing a local file")
    print("-" * 40)

    # This would upload the file and analyze it
    # Uncomment and modify path to test with a real file
    """
    result = client.create_chat('''
        Analyze this data file and summarize the key insights:
        <SHOW_FILE>/path/to/your/data.csv</SHOW_FILE>
    ''')
    
    final = client.wait_for_completion(result["chat_id"])
    print(final["history"]["messages"][-1]["content"])
    """

    # Example 2: Request output at specific locations
    print("\nExample 2: Generating files at specific locations")
    print("-" * 40)

    # This would generate files and save them to specified paths
    # Uncomment and modify paths to test
    """
    result = client.create_chat('''
        Create a simple Python script that prints "Hello, World!"
        and save it to:
        <GENERATE_FILE>/tmp/hello_world.py</GENERATE_FILE>
        
        Also create a README explaining how to run it:
        <GENERATE_FILE>/tmp/README.md</GENERATE_FILE>
    ''')
    
    final = client.wait_for_completion(result["chat_id"])
    
    # Files are now at /tmp/hello_world.py and /tmp/README.md
    print("Files generated!")
    print(final["history"]["messages"][-1]["content"])
    """

    # Example 3: Complex workflow with input and output files
    print("\nExample 3: Input file → Processing → Output files")
    print("-" * 40)

    """
    result = client.create_chat('''
        I have sales data that needs analysis:
        <SHOW_FILE>/home/user/sales_2025.csv</SHOW_FILE>
        
        Please:
        1. Analyze trends and patterns
        2. Create a summary report: <GENERATE_FILE>/home/user/reports/sales_summary.pdf</GENERATE_FILE>
        3. Generate a visualization: <GENERATE_FILE>/home/user/reports/sales_chart.png</GENERATE_FILE>
    ''')
    
    final = client.wait_for_completion(result["chat_id"], timeout_seconds=300)
    
    if final["status"] == "completed":
        print("Analysis complete!")
        print("Files saved to:")
        print("  - /home/user/reports/sales_summary.pdf")
        print("  - /home/user/reports/sales_chart.png")
    """

    print("\nNote: Uncomment the examples above and provide real file paths to test.")


if __name__ == "__main__":
    main()
