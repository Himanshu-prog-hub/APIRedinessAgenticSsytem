# Agentic Lens

Agentic Lens evaluates an OpenAPI or Swagger specification across five dimensions: semantic clarity, promptability, workflow composability, schema explainability, and error predictability. It returns a weighted score and a PDF report.

## Run locally

1. Create and activate a Python virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Set `GOOGLE_API_KEY` and optionally `MODEL` (defaults to `gemini-2.5-flash`) as environment variables or in the ignored local file `root_agent/.env`. For LangSmith tracing, add `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, and optionally `LANGSMITH_PROJECT` there too.
4. Start the app with `python app.py` and open `http://localhost:8080`.

The evaluator runs in-process; there is no separate ADK server.

To evaluate promptability with examples, upload a `.txt` or `.md` file alongside the specification, or provide its GitHub path in GitHub mode. `prompts.txt` is an example input; it is not loaded automatically.

## Architecture and interview notes

See [ARCHITECTURE_AND_INTERVIEW.md](ARCHITECTURE_AND_INTERVIEW.md) for the graph, safeguards, limitations, RAG options, evaluation harness, and interview practice answers.
