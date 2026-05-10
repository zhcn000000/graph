from pydantic import BaseModel


class ModelDeps(BaseModel):
    max_result_retries: int = 3
    use_tools: bool = True
