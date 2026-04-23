import sys
import logging
import os

# Configure logging before importing app (which also configures logging)
logging.basicConfig(level=logging.INFO, stream=sys.stdout, force=True)

from app import get_enhanced_query

test_cases = [
    "failed god metallica",
    "lyrics about mom's spaghetti",
    "starboy"
]

print("--- STARTING VERIFICATION ---")
for query in test_cases:
    print(f"\nQuery: '{query}'")
    result = get_enhanced_query(query)
    print(f"Result: '{result}'")

print("\n--- VERIFICATION COMPLETE ---")
