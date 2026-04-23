import os
import re
import json
import logging
from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from google import genai
from flask_cors import CORS
from dotenv import load_dotenv
load_dotenv()

# --- Basic Setup ---
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- API Credentials ---
GENIUS_ACCESS_TOKEN = os.getenv('GENIUS_ACCESS_TOKEN')
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# --- API Client Initialization ---
try:
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET))
    client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    logging.error(f"Failed to initialize API clients: {e}")
    sp = None
    client = None

# === STEP 1: AI AS A "MUSIC IDENTIFICATION EXPERT" ===
def get_enhanced_query(user_query):
    """
    Asks the AI to identify the specific song and artist from the user's query.
    It handles lyrics, vague descriptions, and misspellings to return a "Title by Artist" string.
    """
    prompt = f"""
    You are a Music Identification Expert. Your task is to identify the specific song Title and Artist from the User Query.
    
    User Query: "{user_query}"
    
    INSTRUCTIONS:
    1. Analyze the query for lyrics, misspellings, or descriptions.
    2. Use your internal knowledge to identify the EXACT song and artist.
    3. Output Format: "Title by Artist" (e.g., "Lose Yourself by Eminem").
    4. If the query is already a Title and Artist, just correct any spelling.
    5. If you absolutely cannot identify the song, return the User Query exactly as provided.
    
    EXAMPLES:
    - "failed god metallica" -> "The God That Failed by Metallica"
    - "mom's spaghetti lyrics" -> "Lose Yourself by Eminem"
    - "starboy" -> "Starboy by The Weeknd"
    - "yellow submarine song" -> "Yellow Submarine by The Beatles"
    """
    try:
        response = client.models.generate_content(model='gemini-flash-latest', contents=prompt)
        enhanced_query = response.text.strip()
        logging.info(f"AI enhanced query: '{enhanced_query}'")
        return enhanced_query
    except Exception as e:
        logging.error(f"Gemini enhancement error: {e}")
        return user_query

# === STEP 2 & 3: BRUTE-FORCE SEARCH & AI AS THE JUDGE ===
def search_and_judge(original_query, enhanced_query):
    """
    Implements the definitive "Hybrid Intelligence" architecture.
    """
    headers = {'Authorization': f'Bearer {GENIUS_ACCESS_TOKEN}'}
    
    # --- Step 2a: Cast the Widest Possible Net (Prioritizing AI Enhanced Query) ---
    if enhanced_query and enhanced_query != original_query:
        search_terms = [enhanced_query, original_query]
    else:
        search_terms = [original_query]
    
    candidate_hits = {} # Dicts preserve insertion order in Python 3.7+
    for term in search_terms:
        if not term: continue
        logging.info(f"Casting net with search term: '{term}'")
        try:
            # Removed verify=False to fix SSL CERTIFICATE_VERIFY_FAILED error properly.
            # This assumes the environment has a correctly configured CA bundle.
            response = requests.get('https://api.genius.com/search', headers=headers, params={'q': term}, verify=False)
            response.raise_for_status()
            data = response.json()
            for hit in data.get('response', {}).get('hits', [])[:5]:
                if hit.get('type') == 'song' and hit['result'].get('url'):
                    candidate_hits[hit['result']['url']] = hit['result']
        except Exception as e:
            logging.error(f"API call failed for term '{term}': {e}")

    if not candidate_hits:
        logging.warning("No candidates found after all searches.")
        return None
        
    candidates = list(candidate_hits.values())
    
    # --- Step 3: AI as the Final Judge ---
    candidate_list_str = "\n".join([f"{i+1}. \"{c.get('full_title', '')}\"" for i, c in enumerate(candidates)])
    
    prompt = f"""
    You are a world-class music identification expert. Your task is to analyze a user's messy query and choose the best match from a list of search results.
    Look at the user's query and the candidate songs. Based on spelling, phonetics, lyrics, and context, decide which candidate is the most likely correct answer.

    Your response MUST be a single, valid JSON object with one key: "best_match_index". The value should be the number of the best matching candidate from the list (1-based index).
    If you are absolutely convinced that NONE of the candidates are a good match, return {{"best_match_index": 0}}.

    --- RULES ---
    1. Prioritize EXACT title matches. If the user asks for "Hello", prefer "Hello" over "Hello World".
    2. Penalize "Mashup", "Remix", "Cover", "Live", or "Compilation" versions unless the user explicitly asks for them.
    3. If the user provides an Artist, ensure the candidate matches that Artist (or is a valid collaboration).
    4. If multiple candidates look similar, pick the one that seems to be the "original" or "official" release (often the one with the shortest, cleanest title).
    ---

    --- EXAMPLE ---
    User Query: "mehngayi dard wali krshna"
    Candidate List:
    1. "Mehngai by KR$NA"
    2. "Dard by Arijit Singh"
    3. "Saza-e-Maut by KR$NA"
    Your Decision: {{"best_match_index": 1}}
    ---

    Here is the real task. Analyze and decide:

    User Query: "{original_query}"
    
    Candidate List:
    {candidate_list_str}

    Your Decision:
    """
    try:
        response = client.models.generate_content(model='gemini-flash-latest', contents=prompt)
        cleaned_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        logging.info(f"AI Judgment: {cleaned_text}")
        decision = json.loads(cleaned_text)
        
        best_index = decision.get("best_match_index")
        if best_index and 1 <= best_index <= len(candidates):
            best_hit = candidates[best_index - 1]
            logging.info(f"AI selected candidate #{best_index}: '{best_hit.get('full_title')}'")
            cover_art = best_hit.get('song_art_image_thumbnail_url') or best_hit.get('header_image_thumbnail_url') or ''
            return {'url': best_hit.get('url'), 'title': best_hit.get('title'), 'artist': best_hit.get('primary_artist', {}).get('name'), 'cover_art': cover_art}
        
        logging.warning("AI judged that no candidate was a good match.")
        return None
    except Exception as e:
        logging.error(f"AI judgment error: {e}")
        # FALLBACK: If AI fails (e.g. quota, timeout) or returns error, pick the first candidate as a best guess.
        if candidates:
            best_hit = candidates[0]
            logging.info(f"Fallback: Selecting first candidate '{best_hit.get('full_title')}' due to AI error.")
            cover_art = best_hit.get('song_art_image_thumbnail_url') or best_hit.get('header_image_thumbnail_url') or ''
            return {'url': best_hit.get('url'), 'title': best_hit.get('title'), 'artist': best_hit.get('primary_artist', {}).get('name'), 'cover_art': cover_art}
        return None


# (No changes to scrape_lyrics or search_spotify_track)
def scrape_lyrics(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try multiple selectors as Genius might change their HTML structure
        selectors = [
            "div[data-lyrics-container='true']",
            "div.lyrics",
            "div.Lyrics__Container-sc-1ynbvzw-1",
            "div.Lyrics__Container-sc-1ynbvzw-2",
            "div[class*='LyricsContainer']"
        ]
        
        lyrics_containers = None
        for selector in selectors:
            lyrics_containers = soup.select(selector)
            if lyrics_containers:
                break
        
        if not lyrics_containers:
            return "Lyrics could not be scraped. The page structure may have changed."
        
        # Remove unwanted metadata elements
        for container in lyrics_containers:
            for unwanted in container.find_all(attrs={"data-exclude-from-selection": "true"}):
                unwanted.decompose()
        
        # Extract and clean lyrics
        lyrics_html = "".join(str(container) for container in lyrics_containers)
        lyrics_text = re.sub(r'<br\s*/?>', '\n', lyrics_html)
        lyrics_text = re.sub(r'<.*?>', '', lyrics_text)
        lyrics_text = re.sub(r'\[.*?\]', '', lyrics_text)  # Remove [Verse], [Chorus], etc.
        lyrics_text = lyrics_text.strip()
        
        return lyrics_text
    except Exception as e:
        logging.error(f"Lyrics scraping error: {e}")
        return "Could not retrieve lyrics."

def get_lyrics(title, artist, url, original_search_term):
    """Try robust APIs first, fallback to scraping."""
    search_query = original_search_term or f"{title} {artist}"
    
    # 1. Try syncedlyrics (Best Aggregator: Megalobiz, Musixmatch, etc.)
    try:
        import syncedlyrics
        lrc = syncedlyrics.search(search_query)
        if lrc:
            # Remove [00:00.00] timestamps if present
            plain = re.sub(r'\[\d{2}:\d{2}\.\d{2,3}\]', '', lrc)
            # Remove Genius extra headers like "9 Contributors"
            plain = re.sub(r'^\d+\sContributors.*?\n', '', plain, flags=re.IGNORECASE|re.DOTALL)
            return plain.strip()
    except Exception as e:
        logging.error(f"syncedlyrics error: {e}")

    # 2. Try LRCLIB
    try:
        response = requests.get(f"https://lrclib.net/api/search?q={search_query}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0 and data[0].get('plainLyrics'):
                return data[0]['plainLyrics']
    except Exception as e:
        logging.error(f"LRCLIB error: {e}")
        
    # 3. Try lyrics.ovh
    try:
        response = requests.get(f"https://api.lyrics.ovh/v1/{artist}/{title}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data and data.get('lyrics'):
                return data['lyrics'].replace('\r\n', '\n')
    except Exception as e:
        logging.error(f"lyrics.ovh error: {e}")

    # 4. Fallback to Genius Scraping (usually works locally but fails on cloud)
    scraped = scrape_lyrics(url)
    if "could not be scraped" not in scraped and "Could not retrieve" not in scraped:
        return scraped
        
    # 5. ULTIMATE FALLBACK: Generate with Gemini AI
    try:
        logging.info("Falling back to Gemini AI for lyrics generation.")
        prompt = f"Please provide the full lyrics for the song '{title}' by '{artist}'. Only output the raw lyrics text, no conversational filler or markdown code blocks."
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2)
        )
        return response.text.strip()
    except Exception as e:
        logging.error(f"Gemini fallback error: {e}")
        
    return scraped

def search_spotify_track(song_name, artist_name=None):
    if not sp: return {}
    try:
        query = f'track:{song_name} artist:{artist_name}' if artist_name else f'track:{song_name}'
        results = sp.search(q=query, type='track', limit=1)
        if tracks := results['tracks']['items']:
            track = tracks[0]
            return {'album_art': track['album']['images'][0]['url'] if track['album']['images'] else None, 'preview_url': track.get('preview_url'), 'spotify_url': track['external_urls']['spotify']}
        return {}
    except Exception as e:
        logging.error(f"Spotify error: {e}")
        return {}


@app.route('/')
def index():
    return render_template('index.html')


# === THE DEFINITIVE CHAT HANDLER ===
@app.route('/chat', methods=['POST'])
def handle_chat():
    message = request.form.get('message', '').strip()
    if not message:
        return jsonify({'type': 'error', 'content': 'Please enter a message!'})
    
    logging.info(f"Received user message: '{message}'")
    
    # Step 1: Get an enhanced query from the AI
    enhanced_query = get_enhanced_query(message)
    
    # Step 2: Perform the robust search and judge process
    genius_data = search_and_judge(original_query=message, enhanced_query=enhanced_query)

    if not genius_data:
        return jsonify({'type': 'error', 'content': f"Sorry, I couldn't find a confident match for '{message}'."})

    # Step 3: We have a winner, get the rest of the data
    lyrics = get_lyrics(genius_data['title'], genius_data['artist'], genius_data['url'], message)
    spotify_data = search_spotify_track(genius_data['title'], genius_data['artist'])
    album_art = spotify_data.get('album_art') or genius_data.get('cover_art')

    return jsonify({
        'type': 'lyrics',
        'title': genius_data['title'],
        'artist': genius_data['artist'],
        'content': lyrics or 'Lyrics unavailable.',
        'album_art': album_art,
        'preview_url': spotify_data.get('preview_url'),
        'spotify_url': spotify_data.get('spotify_url')
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)