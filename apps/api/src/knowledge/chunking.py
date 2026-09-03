"""Fixed-size text chunking with overlap."""

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    step = chunk_size - overlap
    while start < len(text):
        chunk = text[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks
