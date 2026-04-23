# Lyrix Chat - Docker Instructions

## Prerequisites
- Docker installed on your machine.

## How to Build the Docker Image
1. Open your terminal in the project directory.
2. Run the following command to build the image:
   ```bash
   docker build -t lyrix-chat .
   ```

## How to Run the Docker Container
1. You need to provide your environment variables. create a file named `.env.docker` with your API keys:
   ```
   GENIUS_ACCESS_TOKEN=your_token_here
   SPOTIFY_CLIENT_ID=your_id_here
   SPOTIFY_CLIENT_SECRET=your_secret_here
   GEMINI_API_KEY=your_key_here
   ```
2. Run the container:
   ```bash
   docker run -p 5000:5000 --env-file .env.docker lyrix-chat
   ```
3. Open your browser and go to `http://localhost:5000`.

## How to Share with Someone
### Option A: Share Source Code
1. Zip the entire project folder (excluding `venv` and `__pycache__`).
2. Send the zip file.
3. The recipient can unzip it and follow the "How to Build" instructions above.

### Option B: Save and Share Image (Advanced)
1. Save the built image to a file:
   ```bash
   docker save -o lyrix-chat.tar lyrix-chat
   ```
2. Send `lyrix-chat.tar` to the recipient.
3. The recipient can load the image:
   ```bash
   docker load -i lyrix-chat.tar
   ```
4. Then they can run it using the "How to Run" command.
