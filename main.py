import os
import json
import tempfile
import subprocess
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="Python Typing & Coding Practice API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------
# Content: Chapters and Exercises (static seed)
# ------------------------------------------------------------
# Each exercise defines: id, title, prompt, starter_code, tests
# tests are simple: run code then evaluate expressions or compare stdout

CHAPTERS: List[Dict[str, Any]] = [
    {
        "id": "basics",
        "title": "Python Basics",
        "description": "Print, variables, and simple expressions",
        "exercises": [
            {
                "id": "print-hello",
                "title": "Print Hello World",
                "prompt": "Write code that prints exactly: Hello, World!",
                "starter_code": "# Write a print statement below\n",
                "tests": {
                    "type": "stdout",
                    "expected": "Hello, World!\n"
                }
            },
            {
                "id": "variables-sum",
                "title": "Variables and Sum",
                "prompt": "Create two variables a = 5 and b = 7 and print their sum.",
                "starter_code": "# Define a and b, then print their sum\n",
                "tests": {
                    "type": "stdout",
                    "expected": "12\n"
                }
            },
        ]
    },
    {
        "id": "functions",
        "title": "Functions",
        "description": "Define and call functions",
        "exercises": [
            {
                "id": "def-add",
                "title": "Define add(a, b)",
                "prompt": "Define a function add(a, b) that returns the sum of a and b.",
                "starter_code": "# Define add(a, b) below\n",
                "tests": {
                    "type": "eval",
                    "checks": [
                        {"expr": "add(2, 3)", "equals": 5},
                        {"expr": "add(-1, 1)", "equals": 0},
                        {"expr": "add(10, 5)", "equals": 15}
                    ]
                }
            },
            {
                "id": "def-greet",
                "title": "Function greet(name)",
                "prompt": "Write a function greet(name) that returns 'Hello, <name>!'.",
                "starter_code": "# Define greet(name) below\n",
                "tests": {
                    "type": "eval",
                    "checks": [
                        {"expr": "greet('Ada')", "equals": "Hello, Ada!"},
                        {"expr": "greet('Bob')", "equals": "Hello, Bob!"}
                    ]
                }
            }
        ]
    },
    {
        "id": "loops",
        "title": "Loops",
        "description": "For and while loops",
        "exercises": [
            {
                "id": "sum-1-to-n",
                "title": "Sum 1..n",
                "prompt": "Read n from a variable and print the sum from 1 to n (inclusive). Assume n = 5.",
                "starter_code": "# Set n and print the sum from 1 to n\n# Example: if n = 5, output should be 15\n",
                "tests": {
                    "type": "stdout_with_preset",
                    "preset": "n = 5\n",
                    "expected": "15\n"
                }
            }
        ]
    }
]

# ------------------------------------------------------------
# Models
# ------------------------------------------------------------
class EvaluateRequest(BaseModel):
    chapter_id: str = Field(...)
    exercise_id: str = Field(...)
    code: str = Field(..., description="User submitted code")

class EvaluateResult(BaseModel):
    passed: bool
    feedback: str
    details: Any = None

# ------------------------------------------------------------
# Helper: find exercise
# ------------------------------------------------------------
def find_exercise(chapter_id: str, exercise_id: str) -> Dict[str, Any]:
    for ch in CHAPTERS:
        if ch["id"] == chapter_id:
            for ex in ch["exercises"]:
                if ex["id"] == exercise_id:
                    return ex
    return None

# ------------------------------------------------------------
# Secure-ish subprocess runner
# ------------------------------------------------------------
PYTHON_EXEC = "python"

def run_user_code_capture_stdout(code: str, preset: str = "", timeout: float = 2.0) -> Dict[str, Any]:
    """Run code in a separate python process and capture stdout. No input allowed."""
    final_code = preset + "\n" + code
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tmp:
        tmp.write(final_code)
        tmp_path = tmp.name
    try:
        proc = subprocess.run(
            [PYTHON_EXEC, "-S", tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": 124, "stdout": "", "stderr": "Execution timed out"}
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


def run_user_code_and_eval(code: str, checks: List[Dict[str, Any]], timeout: float = 2.0) -> Dict[str, Any]:
    """Run code, then evaluate expressions in the same process to check results.
    We do this by creating a small harness file that execs the code into a dict namespace,
    then evaluates each expression and prints a JSON result to stdout.
    """
    harness = f"""
import json
results = []
ns = {{}}
try:
    exec(compile({code!r}, '<user>', 'exec'), ns, ns)
    ok = True
    for item in {json.dumps(checks)}:
        expr = item.get('expr')
        expected = item.get('equals')
        try:
            val = eval(expr, ns, ns)
            eq = (val == expected)
            results.append({{'expr': expr, 'value': val, 'expected': expected, 'pass': eq}})
            if not eq:
                ok = False
        except Exception as e:
            ok = False
            results.append({{'expr': expr, 'error': str(e), 'pass': False}})
    print(json.dumps({{'ok': ok, 'results': results}}))
except Exception as e:
    print(json.dumps({{'ok': False, 'error': str(e), 'results': []}}))
"""
    out = run_user_code_capture_stdout(harness, preset="", timeout=timeout)
    try:
        data = json.loads(out.get("stdout") or "{}")
    except json.JSONDecodeError:
        data = {"ok": False, "error": (out.get("stderr") or "Invalid output")}
    data["stderr"] = out.get("stderr")
    data["returncode"] = out.get("returncode")
    return data

# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------
@app.get("/")
def read_root():
    return {"message": "Python Typing Practice API"}

@app.get("/chapters")
def list_chapters():
    # Expose chapters without internal test details for brevity
    slim = []
    for ch in CHAPTERS:
        slim.append({
            "id": ch["id"],
            "title": ch["title"],
            "description": ch["description"],
            "exercises": [{"id": ex["id"], "title": ex["title"]} for ex in ch["exercises"]]
        })
    return {"chapters": slim}

@app.get("/chapters/{chapter_id}")
def get_chapter(chapter_id: str):
    for ch in CHAPTERS:
        if ch["id"] == chapter_id:
            # include prompt and starter for each exercise
            return {
                "id": ch["id"],
                "title": ch["title"],
                "description": ch["description"],
                "exercises": [
                    {
                        "id": ex["id"],
                        "title": ex["title"],
                        "prompt": ex["prompt"],
                        "starter_code": ex["starter_code"],
                    } for ex in ch["exercises"]
                ]
            }
    raise HTTPException(status_code=404, detail="Chapter not found")

@app.post("/evaluate", response_model=EvaluateResult)
def evaluate(req: EvaluateRequest):
    ex = find_exercise(req.chapter_id, req.exercise_id)
    if not ex:
        raise HTTPException(status_code=404, detail="Exercise not found")

    tests = ex.get("tests", {})
    ttype = tests.get("type")

    if ttype == "stdout":
        out = run_user_code_capture_stdout(req.code)
        ok = (out["returncode"] == 0 and out["stdout"] == tests.get("expected"))
        feedback = "Great job!" if ok else (
            f"Expected output: {tests.get('expected')!r}, but got: {out['stdout']!r}. "
            + (f"Error: {out['stderr']}" if out.get('stderr') else "")
        )
        return EvaluateResult(passed=ok, feedback=feedback, details=out)

    if ttype == "stdout_with_preset":
        preset = tests.get("preset", "")
        out = run_user_code_capture_stdout(req.code, preset=preset)
        ok = (out["returncode"] == 0 and out["stdout"] == tests.get("expected"))
        feedback = "Nice!" if ok else (
            f"Expected output: {tests.get('expected')!r}, but got: {out['stdout']!r}. "
            + (f"Error: {out['stderr']}" if out.get('stderr') else "")
        )
        return EvaluateResult(passed=ok, feedback=feedback, details=out)

    if ttype == "eval":
        checks = tests.get("checks", [])
        res = run_user_code_and_eval(req.code, checks=checks)
        ok = bool(res.get("ok"))
        if ok:
            feedback = "All tests passed!"
        else:
            # build readable feedback
            msgs = []
            for r in res.get("results", []) or []:
                if not r.get("pass"):
                    if "error" in r:
                        msgs.append(f"{r['expr']}: error {r['error']}")
                    else:
                        msgs.append(f"{r['expr']}: expected {r['expected']!r}, got {r['value']!r}")
            if not msgs and res.get("error"):
                msgs.append(str(res["error"]))
            feedback = "; ".join(msgs) if msgs else "Some tests failed."
        return EvaluateResult(passed=ok, feedback=feedback, details=res)

    raise HTTPException(status_code=400, detail="Unknown test type")

@app.get("/test")
def test_database():
    """Basic health endpoint with database env visibility"""
    response = {
        "backend": "✅ Running",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
    }
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
