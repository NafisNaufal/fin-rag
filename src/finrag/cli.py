import argparse
import json
from pathlib import Path

from finrag.config import Settings
from finrag.models import GrowthRequest, Question
from finrag.service import Library


def main():
    parser = argparse.ArgumentParser(prog="finrag")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Start the local web app")
    serve.add_argument("--port", type=int, default=8000)
    ingest = sub.add_parser("ingest", help="Parse and index one PDF")
    ingest.add_argument("pdf", type=Path)
    ingest.add_argument("--company", default="")
    ingest.add_argument("--year", type=int)
    for command in ("search", "ask"):
        p = sub.add_parser(command)
        p.add_argument("question")
        p.add_argument("--document-id")
        p.add_argument("--top-k", type=int, default=5)
    evaluate = sub.add_parser("evaluate", help="Measure document/page retrieval recall")
    evaluate.add_argument("dataset", type=Path)
    evaluate.add_argument("--top-k", type=int, default=5)
    answer_eval = sub.add_parser("evaluate-answers", help="Run answer generation for human review")
    answer_eval.add_argument("dataset", type=Path)
    answer_eval.add_argument("--top-k", type=int, default=5)
    growth = sub.add_parser("growth", help="Calculate change from an exact report table row")
    growth.add_argument("document_id")
    growth.add_argument("metric")
    growth.add_argument("from_year", type=int)
    growth.add_argument("to_year", type=int)
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn

        uvicorn.run("finrag.api:create_app", factory=True, host="127.0.0.1", port=args.port)
        return
    library = Library(Settings())
    try:
        if args.command == "ingest":
            result = library.ingest(args.pdf, args.pdf.name, args.company, args.year)
            print(result.model_dump_json(indent=2, exclude={"blocks"}))
        elif args.command == "evaluate":
            from finrag.evaluation import evaluate

            print(json.dumps(evaluate(library, args.dataset, args.top_k), indent=2))
        elif args.command == "evaluate-answers":
            from finrag.evaluation import evaluate_answers

            print(json.dumps(evaluate_answers(library, args.dataset, args.top_k), indent=2))
        elif args.command == "growth":
            result = library.growth(
                GrowthRequest(
                    document_id=args.document_id,
                    metric=args.metric,
                    from_year=args.from_year,
                    to_year=args.to_year,
                )
            )
            print(result.model_dump_json(indent=2))
        else:
            question = Question(
                question=args.question, document_id=args.document_id, top_k=args.top_k
            )
            if args.command == "search":
                print(json.dumps([s.model_dump() for s in library.search(question)], indent=2))
            else:
                print(library.ask(question).model_dump_json(indent=2))
    finally:
        library.close()
