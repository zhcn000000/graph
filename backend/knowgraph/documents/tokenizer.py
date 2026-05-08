import os
from collections import Counter
from functools import lru_cache

from transformers.models.auto.tokenization_auto import AutoTokenizer

HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
os.environ["HF_ENDPOINT"] = HF_ENDPOINT


@lru_cache(maxsize=1)
def get_tokenizer():
    return AutoTokenizer.from_pretrained("BAAI/bge-m3")


async def atokenize_content(content: str) -> Counter[int]:
    tokens = get_tokenizer().tokenize(content)
    ids = get_tokenizer().convert_tokens_to_ids(tokens)
    if isinstance(ids, int):
        ids = [ids]
    return Counter(ids)
