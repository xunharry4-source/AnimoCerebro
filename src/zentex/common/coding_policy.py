"""
Zentex Coding Policy — enforced conventions for engineering changes.

This module documents mandatory rules. Import it nowhere; it exists as the
canonical reference point for inline ``# POLICY`` comments throughout the
codebase.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POLICY[no-silent-except]  — NEVER swallow an exception silently
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ FORBIDDEN — zero visibility, impossible to debug in production:

    except Exception:
        logger.error("Describe the failure", exc_info=True)
        raise

    except Exception:
        continue

    except Exception:
        return None   # or {}, [], False, ""

    except Exception as e:
        return ServiceResponse.error(...)   # no logger call

✅ REQUIRED — every except block must emit at least one log line:

    # If the caller can continue with a fallback value:
    except Exception:
        logger.warning("Short description of what failed", exc_info=True)
        return fallback_value

    # If the error is expected (e.g. optional dependency, network probe):
    except Exception:
        logger.debug("Short description — expected failure path", exc_info=True)
        return fallback_value

    # If the caller must abort:
    except Exception:
        logger.error("Short description", exc_info=True)

RATIONALE:
    Silent ``except: pass`` is banned because it fabricates a healthy runtime
    state, destroys root-cause visibility, and turns real backend failures into
    fake "no data" outcomes.
        raise

Rules:
  1. ``exc_info=True`` is mandatory so the full traceback appears in logs.
  2. Choose level by severity:
       - DEBUG  : expected / informational (probe fail, optional dep absent)
       - WARNING: unexpected but recoverable (DB row corrupt, file unreadable)
       - ERROR  : unexpected and causes visible user-facing failure
  3. ``logger.exception(msg)`` is equivalent to ``logger.error(msg, exc_info=True)``
     and is preferred for brevity in error paths that always abort.
  4. The only allowed silent excepts are narrow type catches for optional
     imports at module level (``except ImportError``), and must carry a
     ``# pragma: no cover`` comment.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POLICY[no-bare-logger-error]  — always include exc_info inside except blocks
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ FORBIDDEN — message only, traceback lost:

    except Exception as e:
        logger.error(f"Something failed: {e}")

✅ REQUIRED:

    except Exception as e:
        logger.error(f"Something failed: {e}", exc_info=True)
        # or equivalently:
        logger.exception("Something failed")

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POLICY[no-fake-impl]  — NEVER pretend a feature works when it does not
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A fake implementation is any non-abstract method whose body does nothing
useful: it returns a hardcoded empty value, always returns True/False, or
has a bare ``pass`` body — without any comment explaining why.

Fake implementations are MORE dangerous than honest errors because:
  - Callers assume the feature works and make decisions based on wrong data.
  - Security checks that always pass grant implicit approval to every action.
  - Audit trails that always return [] hide all violations.
  - The system appears healthy in logs while silently providing no protection.

❌ FORBIDDEN — silent fake that misleads every caller:

    def get_audit_trail(self, limit: int = 50) -> List[Dict]:
        # For now, return a placeholder
        return []

    def _check_resource_limits(self, context: dict) -> bool:
        # For now, we'll just return True as a placeholder
        return True

    def inspect_history(self, n: int = 1) -> None:
        pass

✅ REQUIRED options (choose one):

    # Option A — implement it for real (preferred):
    def get_audit_trail(self, limit: int = 50) -> List[Dict]:
        return self._gate.get_audit_log()[-limit:]

    # Option B — raise NotImplementedError so callers know it is not ready:
    def _check_resource_limits(self, context: dict) -> bool:
        raise NotImplementedError(
            "_check_resource_limits is not yet implemented. "
            "Do not merge until this is replaced with real resource monitoring."
        )

    # Option C — if the feature is intentionally disabled, document it
    # explicitly so a future reader knows it was a deliberate choice:
    def list_model_feature_tests(self) -> List[CatalogItem]:
        # Intentionally empty: LLM invocation removed from web console (HTTP 410).
        # Add items here when a replacement test harness is available.
        return []

Rules:
  1. Every ``pass`` body in a non-abstract, non-trivial method is a red flag.
     Either implement it or raise NotImplementedError with a clear message.
  2. Security-critical checks (rate limits, resource limits, access control)
     MUST fail-closed (deny) when the real check cannot be performed.
     Failing open (return True) makes them useless.
  3. Audit functions MUST query real storage. Returning [] silently means
     every audit shows a clean record regardless of what happened.
  4. Mark every intentional stub with:
       # POLICY[no-fake-impl]: <reason this is intentionally a no-op>
     so code reviewers and AI assistants do not mistake it for a bug.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POLICY[no-custom-db-logic] — NEVER reinvent database read/write logic
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ FORBIDDEN — implementing direct DB access or custom rules in tests/modules:

    # Re-implementing DAO logic in a test script
    def read_tasks_from_sqlite():
        conn = sqlite3.connect(...)
        return conn.execute("SELECT * FROM tasks")

✅ REQUIRED — always use established system layers:

    from zentex.tasks.dao import TaskDAO
    dao = TaskDAO(db_path=...)
    tasks = dao.list_tasks()

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POLICY[no-mocks-in-validation] — NEVER use mocks/forgery for evidence
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ FORBIDDEN — using Mock or simulated推演 to prove a feature works:

    from unittest.mock import MagicMock
    plugin_service = MagicMock()
    plugin_service.get_plugins.return_value = [...]

✅ REQUIRED — use real components via CLI or system entry points:

    # Run the real command and check physical outputs
    # Verifying real file/DB state
    # (CLI testing is the primary evidence)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POLICY[no-forged-data-sources] — NEVER create temporary or fake DBs/files
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ FORBIDDEN — creating local SQLite files or data sources to simulate state:

    # FORBIDDEN: creating a fake DB path in a script to bypass real environment
    db_path = "scripts/authentic_plugins.sqlite3" 
    storage = PluginStorage(db_path)
    storage.upsert_plugin(...)

✅ REQUIRED — interact with the AUTHENTIC system state and real data sources:

    # REQUIRED: Use the real system path or the established service singleton
    from zentex.plugins.service import get_service
    service = get_service()
    
    # Check real records in the actual development/runtime database
    plugins = service.query_plugins_by_lifecycle(lifecycle_status="active")

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POLICY[service-only-execution] — ONLY call service.py for execution
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ FORBIDDEN — bypassing the service layer to trigger logic:

    # FORBIDDEN: calling internal executors or DAOs directly in tests
    from zentex.tasks.executor import InternalPluginExecutor
    executor.execute(...)

✅ REQUIRED — use the public service entry point:

    from zentex.tasks import TaskManagementService
    service = TaskManagementService(...)
    service.run_worker_cycle()

RATIONALE:
    The Service layer is the only contract guaranteed to uphold system 
    invariants, logging, and security. Bypassing it creates "clean room" 
    tests that do not reflect real-world operational failure modes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POLICY[api-request-only] — ONLY use requests for API testing
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ FORBIDDEN — using internal app clients (e.g. FastAPI TestClient):

    from fastapi.testclient import TestClient
    client = TestClient(app)
    response = client.post("/api/task")

✅ REQUIRED — use the 'requests' library to perform authentic HTTP calls:

    import requests
    response = requests.post("http://localhost:8000/api/task", json=data)

RATIONALE:
    Internal test clients bypass the real network stack, middleware, and 
    authentication layers. Only real HTTP requests verify the full 
    end-to-end connectivity and protocol handling.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POLICY[pure-plugin-group-containers] — Plugin group directories must NOT contain code
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ FORBIDDEN — adding Python files directly to plugin group roots:

    src/plugins/nine_questions/
      ├── _partial_failure.py  <-- ❌ VIOLATION
      ├── q1_where_am_i/
      └── q2_asset_inventory/

✅ REQUIRED — place all shared helpers in the official shared location:

    src/zentex/common/nine_questions_shared.py  <-- ✅ CORRECT

RATIONALE:
    Plugin group directories (like nine_questions) are pure containers. 
    Adding logic there breaks architectural rules, bypasses oversight, 
    and leads to hidden "shadow utilities" that are hard to audit and maintain.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POLICY[single-source-only] — EXACTLY one authoritative source is allowed
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For any business fact, runtime state, configuration, prompt contract, schema,
or policy decision, there MUST be exactly one authoritative source.

Secondary sources are forbidden. This includes duplicate databases, shadow
files, compatibility blobs, fallback snapshots, copied constants, alternate
prompt/schema definitions, and sync-by-convention mirrors.

❌ FORBIDDEN — keeping multiple sources and reconciling them later:

    sqlite_status = plugin_storage.get_status(plugin_id)
    json_status = legacy_manifest["lifecycle_status"]

    if sqlite_status != json_status:
        reconcile_status(sqlite_status, json_status)

✅ REQUIRED — read and write the canonical source only:

    status = plugin_storage.get_status(plugin_id)

Rules:
  1. Do not add a second source for a field, decision, schema, prompt contract,
     runtime state, or policy result that already has a canonical source.
  2. When multiple sources already exist, delete the non-authoritative sources
     or migrate their data into the canonical source before claiming completion.
  3. Do not preserve duplicate sources by adding synchronization,
     reconciliation, fallback selection, or "compatibility" merge logic.
  4. Tests must verify the canonical source path. A test that writes to or
     asserts against a secondary source does not prove the real system works.
"""
