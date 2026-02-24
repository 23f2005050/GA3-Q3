from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from io import StringIO
import sys
import traceback
import os
import json
import re
from openai import OpenAI

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CodeRequest(BaseModel):
    code: str

def execute_python_code(code: str) -> dict:

    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        exec(code)
        output = sys.stdout.getvalue()
        return {"success": True, "output": output}

    except Exception:
        output = traceback.format_exc()
        return {"success": False, "output": output}

    finally:
        sys.stdout = old_stdout


# ✅ FIXED PARSER (CRITICAL)
def extract_error_lines(traceback_text: str) -> List[int]:

    matches = re.findall(r'File "", line (\d+)', traceback_text)

    return [int(line) for line in matches]


def analyze_error_with_ai(code: str, traceback_text: str) -> List[int]:

    client = OpenAI(
        api_key=os.environ.get("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1"
    )

    prompt = f"""
Analyze this Python code and its traceback.

CODE:
{code}

TRACEBACK:
{traceback_text}

Return ONLY JSON:
{{"error_lines": [line_numbers]}}
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    text_output = response.choices[0].message.content

    try:
        data = json.loads(text_output)
        return data.get("error_lines", [])

    except json.JSONDecodeError:
        return []


@app.post("/code-interpreter")
def code_interpreter(request: CodeRequest):

    execution_result = execute_python_code(request.code)

    if execution_result["success"]:
        return {
            "error": [],
            "result": execution_result["output"]
        }

    # ✅ FIRST → deterministic parsing
    error_lines = extract_error_lines(execution_result["output"])

    # ✅ OPTIONAL fallback → AI
    if not error_lines:
        error_lines = analyze_error_with_ai(
            request.code,
            execution_result["output"]
        )

    return {
        "error": error_lines,
        "result": execution_result["output"]
    }