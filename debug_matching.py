import os
import requests
import json
import time
from google import genai
from dotenv import load_dotenv

load_dotenv(override=True)

GENIUS_ACCESS_TOKEN = os.getenv('GENIUS_ACCESS_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

client = genai.Client(api_key=GEMINI_API_KEY)

def debug_search(term):
    if not term: return []
    headers = {'Authorization': f'Bearer {GENIUS_ACCESS_TOKEN}'}
    print(f"\n--- Searching for: '{term}' ---")
    enc_term = requests.utils.quote(term)
    try:
        response = requests.get(f'https://api.genius.com/search?q={enc_term}', headers=headers, verify=False)
        response.raise_for_status()
        data = response.json()
        hits = []
        for hit in data.get('response', {}).get('hits', [])[:5]:
            if hit.get('type') == 'song' and hit['result'].get('url'):
                hits.append(hit['result'])
                print(f"  FOUND: {hit['result']['full_title']}")
        return hits
    except Exception as e:
        print(f"Error searching '{term}': {e}")
        return []

# 1. Search with Original Query
original = "tu chahiye by atif"
hits_original = debug_search(original)

# 2. Search with Likely Enhanced Query
enhanced = "Tu Chahiye Atif Aslam"
hits_enhanced = debug_search(enhanced)

# 3. Check for specific bad results
bad_result_substring = "Mashup"
for h in hits_original + hits_enhanced:
    if bad_result_substring.lower() in h['full_title'].lower():
        print(f"\n!!! FOUND POTENTIAL BAD RESULT: {h['full_title']} from query '{original}' or '{enhanced}'")

# 4. Try to get AI Enhancement (with retry/backoff)
print("\n--- Testing AI Enhancement ---")
try:
    prompt = f"""
    You are a language cleanup tool for music searches. Your task is to take a user's potentially misspelled or lyrical query and return the most likely correct song title and artist as a single string.
    Focus on correcting spelling and identifying the core entities. Do not add extra words.
    
    Now, clean up this query: "{original}"
    """
    response = client.models.generate_content(model='gemini-flash-latest', contents=prompt)
    print(f"AI Enhanced Result: '{response.text.strip()}'")
except Exception as e:
    print(f"AI Enhancement failed (Quota?): {e}")

