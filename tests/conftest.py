import hashlib
import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finrag.api import create_app
from finrag.config import Settings
from finrag.service import Library


class FakeEmbeddings:
    """Deterministic vectors isolate persistence/API tests from model downloads."""

    def documents(self, texts):
        return [self.query(t) for t in texts]

    def query(self, text):
        vector = [0.0] * 64
        for word in text.lower().split():
            vector[int(hashlib.sha256(word.encode()).hexdigest()[:8], 16) % 64] += 1
        return vector


@pytest.fixture
def pdf(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "demo", Path(__file__).parents[1] / "scripts/create_demo.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_demo(tmp_path / "demo.pdf")


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data", _env_file=None)


@pytest.fixture
def library(settings):
    lib = Library(settings, embeddings=FakeEmbeddings())
    yield lib
    lib.close()


@pytest.fixture
def client(settings, library):
    with TestClient(create_app(settings, library)) as client:
        yield client
