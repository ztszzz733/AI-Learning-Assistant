# Book-Grounded Learning Agent

[中文](README.md)

A web-based AI learning assistant grounded in PDF book content. This README keeps only the steps needed to set up the environment and run the project from scratch.

## 1. Get the Project

```powershell
git clone <your-repo-url>
cd <your-repo-folder>
```

If you are already in the project directory, continue with the next step.

## 2. Create a Python Environment

Python 3.12 or later is recommended.

Using Conda:

```powershell
conda create -n book-agent python=3.12
conda activate book-agent
```

Or using venv:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## 3. Install Dependencies

Run this from the project root:

```powershell
python -m pip install -e .
```

To install development and test dependencies:

```powershell
python -m pip install -e ".[dev]"
```

## 4. Start the Server

```powershell
python -m book_agent.main --port 8001
```

If you want to run it directly through Conda:

```powershell
conda run --no-capture-output -n book-agent python -m book_agent.main --port 8001
```

If the port is already in use, choose another one:

```powershell
python -m book_agent.main --port 8002
```

## 5. Open the Web App

Open this URL in your browser:

```text
http://127.0.0.1:8001/app
```

API documentation:

```text
http://127.0.0.1:8001/docs
```

## 6. Configure the LLM

In the web app, fill in the model settings panel:

- API Key
- Base URL
- Model
- Reasoning effort, optional
- Thinking type, optional

DeepSeek example:

```text
Base URL: https://api.deepseek.com
Model: deepseek-v4-flash
```

You can also use any other OpenAI-compatible Base URL and model name.

## 7. Start Learning

1. Save the model settings in the web app.
2. Enter the local PDF path in the new study form.
3. Select a learning mode.
4. Create a learning session.
5. Open the session and generate the current lesson.

The PDF path must be accessible from the machine running the backend service. For example:

```text
D:\books\python.pdf
```

## 8. Optional: Run Tests

```powershell
python -m pytest -q
```

Optional JavaScript syntax check:

```powershell
node --check book_agent\web\app.js
```

## License

MIT License. See [LICENSE](LICENSE).
