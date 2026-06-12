"""Mock LLM used for offline deployment testing."""
import random
import time


MOCK_RESPONSES = {
    "default": [
        "This is a mock AI response. In production this can be replaced by OpenAI or another LLM provider.",
        "The production agent is running correctly and handled your request.",
        "Your request was processed by the deployed AI agent.",
    ],
    "docker": [
        "Docker packages the application and dependencies into a repeatable container image."
    ],
    "deploy": [
        "Deployment means moving the application from a local machine to a server or cloud platform."
    ],
    "redis": [
        "Redis stores shared state such as conversation history, rate-limit counters, and budget usage."
    ],
    "health": [
        "The health endpoint lets the platform check whether the process is alive."
    ],
}


def ask(question: str, delay: float = 0.03) -> str:
    time.sleep(delay + random.uniform(0, 0.02))
    question_lower = question.lower()
    for keyword, responses in MOCK_RESPONSES.items():
        if keyword in question_lower:
            return random.choice(responses)
    return random.choice(MOCK_RESPONSES["default"])


def ask_stream(question: str):
    for word in ask(question).split():
        time.sleep(0.02)
        yield word + " "
