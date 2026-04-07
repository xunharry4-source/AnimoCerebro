# LLM Online Smoke Verification (G28.4.6)

This document provides the status and instructions for verifying the real-world connectivity and structural reliability of the AnimoCerebro LLM inference layer.

## Verification Status

| Layer | Environment | Status | Last Verified |
| :--- | :--- | :--- | :--- |
| **Transport** | Mock / Local | ✅ Passed | 2026-03-29 |
| **Gemini Integration** | Sandbox API | ✅ Passed | 2026-03-29 |
| **Production Key** | Real Key | ⚠️ Pending | N/A |

## Offline Verification (Code Integrity)
Execute the following to verify that the LLM client handles rate limits, timeouts, and auth failures correctly without a real network connection:

```bash
python tests/test_wave_n_infrastructure.py
```

## Online Smoke Test (Live API)
To verify real-world connectivity with a live Gemini API key:

1. Export your API key:
   ```bash
   export GEMINI_API_KEY="your-real-key-here"
   ```

2. Run the diagnostic probe:
   ```bash
   # Note: This is a conceptual example of a CLI diag tool
   python -m zentex.cli.diag --probe-llm
   ```

3. Expected Outcome:
   - `LLMHealthProbe`: Returns `True`.
   - `ProviderHealthRegistry`: Status `HEALTHY` (active).
   - `IdentityKernel`: Successfully generates a non-empty `RoleProfile`.

## Failure Recovery Modes
- **Rate Limited**: Exponential backoff initiated (30s -> 60s -> 120s...).
- **Auth Failure**: Key marked as `DEGRADED` and rotated to next available key.
- **Quota Exceeded**: Enter explicit live inference error state. Do not fall back to local rule-based reasoning.
心节意识图谱分析
