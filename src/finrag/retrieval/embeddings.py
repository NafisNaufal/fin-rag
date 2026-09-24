from threading import Lock

from fastembed import TextEmbedding


class Embeddings:
    def __init__(self, model_name: str, cache_dir: str):
        self.model_name = model_name
        self.cache_dir = cache_dir
        self._model = None
        self._lock = Lock()

    def _get(self):
        if self._model is None:
            self._model = TextEmbedding(
                model_name=self.model_name, cache_dir=self.cache_dir, threads=4
            )
        return self._model

    def documents(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            return [v.tolist() for v in self._get().passage_embed(texts)]

    def query(self, text: str) -> list[float]:
        with self._lock:
            return next(self._get().query_embed(text)).tolist()
