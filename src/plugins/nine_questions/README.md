# Nine-Questions Plugin Group Rule

**STOP! READ THIS BEFORE ADDING ANY CODE HERE.**

## Directory Integrity Policy

This directory (`src/plugins/nine_questions/`) is a **PURE PLUGIN GROUP CONTAINER**. 

1. **NO SHARED CODE**: It is strictly forbidden to add any Python files (`.py`) directly to this directory.
2. **ONLY SUBDIRECTORIES**: This directory must only contain plugin implementation subdirectories (e.g., `q1_where_am_i/`, `q2_who_am_i/`).
3. **MANDATORY SHARED LOCATION**: All shared logic, utilities, or helpers used by multiple Nine-Questions plugins **MUST** be placed in `src/zentex/common/nine_questions_shared.py`.
4. **NO HIDDEN HELPERS**: Do not create files starting with `_` (e.g., `_partial_failure.py`) in this directory to bypass architectural rules.

**VIOLATIONS WILL BE TREATED AS A SYSTEM INTEGRITY THREAT AND AUTOMATICALLY DELETED.**

---
*Enforced by Zentex Clinical Standards.*
