import os
from dotenv import load_dotenv
from google import genai

# Load the API key from .env (never hardcode keys in code)
load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# Google's embedding model — free tier, no cost for a mini-project's usage
MODEL_NAME = "gemini-embedding-001"


import time

BATCH_SIZE = 50
DELAY_BETWEEN_BATCHES = 1.5  # seconds — keeps us safely under 100 requests/minute


def embed_chunks(chunks):
    """
    Take the list of chunks from processor.py and add an "embedding"
    field to each one, sending them to the API in batches with a small
    delay between each batch to stay within the free-tier rate limit.
    """
    for batch_start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[batch_start : batch_start + BATCH_SIZE]
        texts = [chunk["text"] for chunk in batch]

        result = embed_with_retry(texts)

        for chunk, embedding in zip(batch, result.embeddings):
            chunk["embedding"] = embedding.values

        print(f"Embedded {min(batch_start + BATCH_SIZE, len(chunks))}/{len(chunks)} chunks...")
        time.sleep(DELAY_BETWEEN_BATCHES)

    return chunks


def embed_with_retry(texts, max_retries=5):
    """
    Call the embedding API, automatically waiting and retrying if we hit
    a rate limit or a temporary network/server issue.
    """
    for attempt in range(max_retries):
        try:
            return client.models.embed_content(
                model=MODEL_NAME,
                contents=texts
            )
        except Exception as e:
            is_last_attempt = attempt == max_retries - 1
            if is_last_attempt:
                raise

            if "429" in str(e):
                print("Rate limit hit — waiting 10 seconds before retrying...")
                time.sleep(10)
            else:
                print(f"Temporary error ({e}) — waiting 5 seconds before retrying...")
                time.sleep(5)


def embed_query(query_text):
    """
    Turn a single user question into an embedding, the same way chunks
    are embedded, so we can compare the question to the chunks later.
    """
    result = client.models.embed_content(
        model=MODEL_NAME,
        contents=query_text
    )
    return result.embeddings[0].values


if __name__ == "__main__":
    # Quick manual test
    from github_loader import clone_repository
    from processor import load_repository_files, chunk_repository_files

    test_url = input("Enter a public GitHub repository URL: ").strip()
    repo_path = clone_repository(test_url)

    files = load_repository_files(repo_path)
    chunks = chunk_repository_files(files)
    print(f"Embedding {len(chunks)} chunks... (this calls the API, may take a bit)")

    chunks = embed_chunks(chunks)

    print(f"\nDone. Each chunk now has an embedding.")
    print(f"Example: chunk 0 from '{chunks[0]['file_path']}'")
    print(f"Embedding length: {len(chunks[0]['embedding'])} numbers")
    print(f"First 5 values: {chunks[0]['embedding'][:5]}")