import logging
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from finrag.config import Settings
from finrag.models import GrowthRequest, Question
from finrag.service import Library

logger = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None, library: Library | None = None):
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.library = library or Library(config)
        yield
        if library is None:
            app.state.library.close()

    app = FastAPI(title="FinRAG", version="0.1.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.exception_handler(ValueError)
    async def invalid_input(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(KeyError)
    async def missing_document(request: Request, exc: KeyError):
        return JSONResponse(status_code=404, content={"detail": "Report not found."})

    @app.exception_handler(Exception)
    async def failure(request: Request, exc: Exception):
        logger.exception("Request failed", exc_info=exc)
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Processing failed. Check the server log; the first upload requires "
                "internet access to download the embedding model."
            },
        )

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    def status():
        return {
            "status": "ok",
            "answer_mode": config.answer_mode,
            "embedding_model": config.embedding_model,
            "parser": config.parser,
            "generation_model": config.ollama_model if config.answer_mode == "ollama" else None,
        }

    @app.get("/api/documents")
    def documents(request: Request):
        return request.app.state.library.documents()

    @app.post("/api/documents", status_code=201)
    def upload(
        request: Request,
        file: Annotated[UploadFile, File()],
        company: Annotated[str, Form()] = "",
        year: Annotated[int | None, Form()] = None,
    ):
        if len(company) > 200 or (year is not None and not 1900 <= year <= 2100):
            raise ValueError(
                "Use a company name under 200 characters and a year from 1900 to 2100."
            )
        filename = (file.filename or "report.pdf").replace("\\", "/").rsplit("/", 1)[-1][:200]
        if not filename.lower().endswith(".pdf"):
            raise ValueError("Choose a PDF file.")
        config.prepare()
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=config.data_dir / "tmp", suffix=".pdf", delete=False
            ) as temp:
                temp_path = Path(temp.name)
                size = 0
                while chunk := file.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > config.max_upload_mb * 1024 * 1024:
                        raise HTTPException(413, f"PDF exceeds {config.max_upload_mb} MB limit.")
                    temp.write(chunk)
            doc = request.app.state.library.ingest(temp_path, filename, company.strip(), year)
            return doc.model_dump(exclude={"blocks"})
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)
            file.file.close()

    @app.get("/api/documents/{document_id}")
    def document(request: Request, document_id: str):
        return request.app.state.library.document(document_id)

    @app.get("/api/documents/{document_id}/pdf")
    def pdf(request: Request, document_id: str):
        doc = request.app.state.library.document(document_id)
        return FileResponse(
            config.data_dir / "raw" / f"{doc.id}.pdf",
            media_type="application/pdf",
            filename=doc.filename,
            content_disposition_type="inline",
        )

    @app.get("/api/documents/{document_id}/markdown")
    def markdown(request: Request, document_id: str):
        doc = request.app.state.library.document(document_id)
        return FileResponse(
            config.data_dir / "parsed" / f"{doc.id}.md",
            media_type="text/markdown",
            filename=Path(doc.filename).stem + ".md",
        )

    @app.post("/api/search")
    def search(request: Request, question: Question):
        return request.app.state.library.search(question)

    @app.post("/api/ask")
    def ask(request: Request, question: Question):
        return request.app.state.library.ask(question)

    @app.post("/api/calculate/growth")
    def growth(request: Request, calculation: GrowthRequest):
        return request.app.state.library.growth(calculation)

    return app
