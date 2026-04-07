from enum import Enum

from app.config import Settings


class TaskCategory(str, Enum):
    # Deterministic, low-stakes tasks. No editorial judgment required.
    # Examples: RSS parsing, dedup, token counting, breaking scan first pass,
    #           metrics formatting, voice relevance keyword filter.
    MECHANICAL = "mechanical"

    # Language understanding and judgment, but no full editorial voice or deep memory.
    # Examples: alignment scoring (1-5), urgency assignment, image prompt refinement,
    #           daily editorial digest, weekly report, link-drop post generation,
    #           breaking scan second pass confirmation.
    REASONING = "reasoning"

    # Full SUAS editorial voice, 22K token memory context, multi-story pattern recognition.
    # Examples: scheduled pipeline post generation, connect-the-dots posts,
    #           monthly pattern report, voice guide updates.
    EDITORIAL = "editorial"


class ModelRouter:
    """
    Maps task categories to Claude model IDs.

    Model IDs come from Settings (pinned in config, overridable via env var).
    Callers NEVER use string literals — always call router.get_model(TaskCategory.X).
    Changing models = 1 env var change, no code changes.

    Usage:
        router = ModelRouter(get_settings())
        model_id = router.get_model(TaskCategory.EDITORIAL)
        client.messages.create(model=model_id, ...)
    """

    def __init__(self, settings: Settings) -> None:
        self._routes: dict[TaskCategory, str] = {
            TaskCategory.MECHANICAL: settings.model_haiku,
            TaskCategory.REASONING: settings.model_sonnet,
            TaskCategory.EDITORIAL: settings.model_opus,
        }

    def get_model(self, task: TaskCategory) -> str:
        return self._routes[task]
