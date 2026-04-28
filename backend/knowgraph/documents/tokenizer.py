from collections import Counter
from functools import lru_cache

from transformers.models.auto.tokenization_auto import AutoTokenizer


@lru_cache(maxsize=1)
def get_tokenizer():
    return AutoTokenizer.from_pretrained("Qwen/Qwen3-Embedding-8B")


async def atokenize_content(content: str) -> Counter[int]:
    tokens = get_tokenizer().tokenize(content)
    ids = get_tokenizer().convert_tokens_to_ids(tokens)
    if isinstance(ids, int):
        ids = [ids]
    return Counter(ids)
