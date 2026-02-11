"""
CellCog SDK File Handling Example

This example demonstrates how to send files to CellCog for analysis.
Generated files are automatically downloaded to ~/.cellcog/chats/{chat_id}/.
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
    result = client.create_chat(
        prompt='''
            Analyze this data file and summarize the key insights:
            <SHOW_FILE>/path/to/your/data.csv</SHOW_FILE>
        ''',
        notify_session_key="agent:main:main",
        task_label="data-analysis"
    )
    
    # Results delivered to your session automatically
    print(f"Chat created: {result['chat_id']}")
    """

    # Example 2: Request multiple output artifacts
    print("\nExample 2: Generating multiple deliverables")
    print("-" * 40)

    # CellCog generates files and they auto-download to ~/.cellcog/chats/{chat_id}/
    """
    result = client.create_chat(
        prompt='''
            I have sales data that needs analysis:
            <SHOW_FILE>/home/user/sales_2025.csv</SHOW_FILE>
            
            Please:
            1. Analyze trends and patterns
            2. Create a PDF summary report
            3. Generate a chart visualization
        ''',
        notify_session_key="agent:main:main",
        task_label="sales-analysis"
    )
    
    print(f"Chat created: {result['chat_id']}")
    print("Generated files will auto-download when complete.")
    """

    print("\nNote: Uncomment the examples above and provide real file paths to test.")


if __name__ == "__main__":
    main()
