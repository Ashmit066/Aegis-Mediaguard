# Aegis MediaGuard

**Real-Time Sports Rights Intelligence Kernel**

A working proof-of-concept backend that helps sports organizations identify, track, and flag unauthorized use of official sports media across the internet in near real time.

---

## Ubuntu Setup

```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip git
```

## Virtual Environment

```bash
git clone <your-repo-url> aegis_mediaguard
cd aegis_mediaguard
python3.11 -m venv .venv
source .venv/bin/activate
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

## Run the Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Interactive API docs are available at: `http://localhost:8000/docs`

---

## Sample curl Requests

### Health check
```bash
curl http://localhost:8000/health
```

### List official asset catalog
```bash
curl http://localhost:8000/assets | python3 -m json.tool
```

### Analyze an authorized distribution
```bash
curl -X POST http://localhost:8000/reports/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "report_id": "RPT-DEMO-001",
    "discovered_url": "https://www.youtube.com/watch?v=nba_finals_official",
    "platform": "youtube",
    "geo_country": "US",
    "detected_at": "2024-07-15T10:00:00",
    "media_type": "highlight_clip",
    "claimant_org": "RightsScan AI",
    "event_name": "NBA Finals 2024",
    "uploader_handle": "NBA_Official",
    "extracted_fingerprint": "d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6",
    "extracted_watermark": "WM-NBA-010",
    "screenshot_hash": "abc123def456",
    "confidence_hint": 0.95
  }'
```

### Analyze a pirated live stream (urgent)
```bash
curl -X POST http://localhost:8000/reports/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "report_id": "RPT-DEMO-002",
    "discovered_url": "https://www.reddit.com/r/cricket/ipl_live_pirate",
    "platform": "reddit",
    "geo_country": "US",
    "detected_at": "2024-04-10T18:00:00",
    "media_type": "live_stream",
    "claimant_org": "Star Sports Guard",
    "event_name": "IPL 2024",
    "uploader_handle": "cricket_free_stream",
    "extracted_fingerprint": "f0e1d2c3b4a5f6e7d8c9b0a1f2e3d4c5",
    "extracted_watermark": "WM-IPL-200",
    "screenshot_hash": null,
    "confidence_hint": 0.97
  }'
```

### Fetch the audit ledger
```bash
curl http://localhost:8000/ledger | python3 -m json.tool
```

### Verify ledger integrity
```bash
curl http://localhost:8000/ledger/verify
```

---

## Run Tests

```bash
pytest tests/ -v
```

---

## Architecture

```
aegis_mediaguard/
├── app/
│   ├── main.py         # FastAPI app factory, router mount
│   ├── api.py          # All route handlers + pipeline orchestration
│   ├── models.py       # Pydantic models: IncomingReport, OfficialAsset, MatchResult,
│   │                   #   RightsDecision, AnalysisVerdict, LedgerEntry
│   └── config.py       # Settings via pydantic-settings (env-overridable)
├── ingest/
│   ├── schema_guard.py # Strict Pydantic validation; raises SchemaValidationError
│   └── normalizer.py   # Post-validation string normalization (fingerprint case, etc.)
├── identify/
│   ├── fingerprint.py  # Hamming distance on hex strings → similarity score [0,1]
│   ├── watermark.py    # Watermark ID lookup → (detected: bool, boost: float)
│   └── matcher.py      # Scans full catalog, selects best match, applies watermark
├── rights/
│   ├── license_matrix.py  # Platform, region, and date checks → (bool, reason str)
│   └── policy_engine.py   # Aggregates checks into RightsDecision
├── risk/
│   ├── scoring.py      # Integer severity 0–100 from confidence + rights + media type
│   └── verdicts.py     # Maps signals → VerdictType with priority logic
├── workers/
│   └── sandbox.py      # ProcessPoolExecutor wrapper with timeout for heavy matching
├── ledger/
│   └── audit.py        # SHA-256 hash-linked append-only evidence chain
├── data/
│   ├── mock_assets.py  # 5 sports assets (NBA, UEFA, IPL, Wimbledon, FIFA)
│   └── mock_reports.py # 6 pre-built test scenarios
└── tests/
    ├── test_schema.py  # 13 schema + normalization tests
    ├── test_matcher.py # 10 fingerprint + watermark + matcher tests
    ├── test_rights.py  # 6 rights policy tests
    ├── test_verdicts.py# 8 end-to-end verdict tests
    └── test_api.py     # 13 HTTP integration tests
```

### Key design decisions

**No shared state in request handlers.** The API route calls `run_match_in_sandbox()`, which serializes the report to a dict, passes it to a subprocess via `ProcessPoolExecutor`, and deserializes the result. The event loop never blocks on CPU-bound fingerprint work.

**Layered pipeline.** Each stage (ingest → identify → rights → risk → ledger) is a separate module with a clean interface. Swapping the fingerprint algorithm, replacing mock stores with Redis/Postgres, or adding a new verdict type requires touching exactly one file.

**Append-only ledger.** Every stage appends a hash-linked record. The verify endpoint walks the chain and recomputes each SHA-256 to detect any tampering. This is the same principle used in certificate transparency logs.

---

## Verdict Flow

```
POST /reports/analyze
        │
        ▼
  schema_guard.validate_report()
        │ fail → 422 + ledger ANALYSIS_FAILED
        ▼
  normalizer.normalize_report()
        │
        ▼ ledger REPORT_RECEIVED, SCHEMA_VALIDATED, REPORT_NORMALIZED
        │
  sandbox.run_match_in_sandbox()   ← subprocess, timeout protected
        │
        ▼ ledger MATCH_COMPLETED [+ WATERMARK_DETECTED if applicable]
        │
  policy_engine.evaluate_rights()
        │
        ▼ ledger RIGHTS_DECIDED
        │
  verdicts.issue_verdict()
        │
        ▼ ledger VERDICT_ISSUED
        │
  return AnalysisVerdict JSON
```

### Verdict priority table

| Condition | Verdict |
|---|---|
| No catalog asset matches fingerprint threshold | `unknown_asset` |
| Match found, all rights checks pass | `authorized` |
| Live stream + high confidence + rights fail | `urgent_live_leak` |
| Watermark confirmed, only platform wrong, non-perfect fp | `manual_review` |
| Any other rights failure | `suspected_infringement` |

---

## Demo Walkthrough

1. Start the server: `uvicorn app.main:app --reload`
2. Hit `GET /assets` — see the 5 official sports assets.
3. POST the **authorized NBA clip** — verdict: `authorized`, low severity.
4. POST the same fingerprint but with `platform: tiktok` — verdict: `suspected_infringement`.
5. POST the **IPL live stream** with `platform: reddit` — verdict: `urgent_live_leak`, severity ≥ 85.
6. POST the **FIFA World Cup 2022** clip with a 2024 `detected_at` — verdict: `suspected_infringement`, `license_valid: false`.
7. POST a made-up fingerprint — verdict: `unknown_asset`.
8. Hit `GET /ledger` — see every stage recorded in order.
9. Hit `GET /ledger/verify` — chain valid.

---

## Why this architecture is strong for a sports media hackathon

**Realistic domain modeling.** The asset catalog, license matrix, and verdict types map directly to how sports broadcasters actually manage rights — platforms, regions, and validity windows are the real levers. A judge or broadcaster watching the demo immediately recognizes the problem being solved.

**End-to-end in one repo, zero external services.** No Redis, no S3, no message broker needed to demo. The in-memory stores are behind clean interfaces (`get_all_assets()`, `append_event()`), so a judge asking "how would you scale this?" gets a one-sentence answer: swap the store, keep every other module identical.

**The subprocess sandbox is a real engineering choice, not theater.** Perceptual hash libraries (imagehash, chromaprint) are CPU-heavy and occasionally crash on malformed input. Isolating them in a child process with a timeout means the API stays up even if the analysis job dies. This is the same pattern used in production content moderation systems.

**The ledger is legally credible.** A hash-linked, append-only record with a verify endpoint is exactly what a legal team needs to demonstrate chain of custody in a DMCA takedown. It's also a natural extension point — pipe ledger entries to a blockchain anchor or S3 for immutability guarantees.

**50 tests, all green, out of the box.** Coverage spans schema rejection, geo blocking, expired licenses, live-leak escalation, unknown assets, and ledger integrity. This signals to technical judges that the code is built to survive edge cases, not just the happy path.
