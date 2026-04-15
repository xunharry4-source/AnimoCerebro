"""Nine Questions Router Implementation

Facade-first design with modularized components:
- route_handlers.py: Route definitions (<800 lines)
- q_commons.py: Shared service layer
- trace_builder.py: Trace construction
- q_handlers.py: Question-specific logic
"""

# Import new router from route_handlers
from .route_handlers import (
    router,
    QUESTION_TITLES,
    get_latest_nine_questions_report,
)

__all__ = ["router", "QUESTION_TITLES", "get_latest_nine_questions_report"]
