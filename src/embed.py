"""
Chunking + embedding generation via the U-M GPT Toolkit gateway (OpenAI-compatible).

Chunking strategy: split on heading-like boundaries first (Markdown #/##, or
blank-line-separated paragraphs as a fallback), then pack greedily up to
MAX_TOKENS per chunk so related content stays together. This matters more
than it sounds -- for runbooks/KBAs, a chunk that splits mid-procedure makes
the topic-extraction step in the next stage much noisier.
"""
import os
import re
import time
from dotenv import load_dotenv
import tiktoken
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

_client = None


def get_client() -> OpenAI:
    """Lazily construct the OpenAI-compatible client, pointed at the U-M GPT
    Toolkit gateway, so this module can be imported (e.g. for testing
    chunk_document()) without UMGPT_API_KEY set."""
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.environ["UMGPT_API_KEY"],
            base_url=os.environ.get("UMGPT_API_BASE", "https://api.toolkit.umgpt.umich.edu/v1"),
        )
    return _client


EMBEDDING_MODEL = "text-embedding-3-small"  # 1536 dims, matches schema.sql -- confirmed
                                             # embeddings-capable in the UMGPT Toolkit model matrix
MAX_TOKENS_PER_CHUNK = 500
ENCODING = tiktoken.get_encoding("cl100k_base")

HEADING_PATTERN = re.compile(r"^(#{1,6}\s+.+|[A-Z][A-Za-z0-9 /'-]{3,80}:)$", re.MULTILINE)


def count_tokens(text: str) -> int:
    return len(ENCODING.encode(text))


def split_into_sections(text: str) -> list[str]:
    """Split on heading-like lines; falls back to paragraph splitting if no headings found."""
    matches = list(HEADING_PATTERN.finditer(text))
    if not matches:
        return [p for p in text.split("\n\n") if p.strip()]

    sections = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append(text[start:end].strip())
    return [s for s in sections if s]


def pack_chunks(sections: list[str], max_tokens: int = MAX_TOKENS_PER_CHUNK) -> list[str]:
    """Greedily combine small sections together, split large ones further."""
    chunks = []
    current = ""

    for section in sections:
        section_tokens = count_tokens(section)

        if section_tokens > max_tokens:
            # Section itself too big -- hard-split on paragraph boundaries.
            if current:
                chunks.append(current)
                current = ""
            sub_parts = section.split("\n\n")
            buf = ""
            for part in sub_parts:
                if count_tokens(buf + "\n\n" + part) > max_tokens and buf:
                    chunks.append(buf)
                    buf = part
                else:
                    buf = f"{buf}\n\n{part}" if buf else part
            if buf:
                chunks.append(buf)
            continue

        if count_tokens(current + "\n\n" + section) > max_tokens and current:
            chunks.append(current)
            current = section
        else:
            current = f"{current}\n\n{section}" if current else section

    if current:
        chunks.append(current)

    return chunks


def chunk_document(raw_text: str) -> list[str]:
    sections = split_into_sections(raw_text)
    return pack_chunks(sections)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=30))
def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of chunk texts. Retries with backoff on transient API errors."""
    response = get_client().embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


def embed_chunks(chunks: list[str], batch_size: int = 100) -> list[list[float]]:
    """Embed all chunks for a document, batching to stay under API request limits."""
    all_embeddings = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        all_embeddings.extend(embed_batch(batch))
        time.sleep(0.1)  # gentle rate-limit pacing
    return all_embeddings