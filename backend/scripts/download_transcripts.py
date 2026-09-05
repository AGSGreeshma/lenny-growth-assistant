import os
import requests


TRANSCRIPTS_DIR = "agent_transcripts"


def download_transcript(url, filename):
    os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

    response = requests.get(url)
    response.raise_for_status()

    filepath = os.path.join(TRANSCRIPTS_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as file:
        file.write(response.text)

    print(f"Downloaded: {filename}")


if __name__ == "__main__":
    print("Transcript downloader is ready.")