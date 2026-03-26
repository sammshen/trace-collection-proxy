# Trace Overview

All traces were collected via the instrumented proxy (`instrumented_proxy.py`) against **MiniMaxAI/MiniMax-M2.5**.

Boot sequences (openclaw `/new`/`/reset` startup) have been stripped from task traces and collected into `boot_sequences_trace.jsonl`.

| Trace | Requests | Responses | Turns | Tool Use | Duration | Topic |
|-------|----------|-----------|-------|----------|----------|-------|
| ai_fashion_industry | 34 | 34 | 34 | Yes | 105s | AI fashion industry research |
| deepseek_sentiment | 16 | 16 | 16 | Yes | 47s | Sentiment analysis |
| estimate_clinical_population | 18 | 18 | 18 | Yes | 126s | Clinical population estimation |
| financial_analysis | 11 | 12 | 11 | Yes | 64s | Financial analysis |
| interview_schedule | 14 | 14 | 14 | Yes | 143s | Interview scheduling |
| japan_trip | 3 | 3 | 3 | Yes | 17s | Japan trip planning |
| my_session | 1 | 1 | 1 | No | 1s | Test (hello) |
| nyc_house | 8 | 8 | 8 | Yes | 38s | NYC house search |
| openclaw_llm_research | 6 | 6 | 6 | Yes | 179s | LLM research |
| price_optimization | 19 | 19 | 19 | Yes | 54s | Price optimization |
| tech_consulting | 8 | 8 | 8 | Yes | 79s | Tech consulting |
| test_multiturn | 4 | 4 | 4 | No | 2s | Multi-turn test (capital of France) |
| yc_search | 30 | 30 | 30 | Yes | 73s | YC company search |
| boot_sequences | 7 | 7 | 7 (3 sessions) | Yes | 1s | Openclaw startup sequences |

**Totals:** 179 requests, 180 responses, 14 traces

## Notes

- **Boot sequences**: Three traces (ai_fashion_industry, tech_consulting, yc_search) originally included openclaw boot sequences (`/new`/`/reset` startup). These have been stripped and combined into `boot_sequences_trace.jsonl`.
- **Agentic tool-use loops**: Most traces are single agentic conversations where the LLM makes repeated tool calls. Each turn re-sends the full conversation history, so the messages array grows each round-trip.
- **financial_analysis** has a request/response count mismatch (11 req / 12 resp) — likely a duplicate or orphaned response record.
- **my_session** and **test_multiturn** are simple non-agentic traces without tool calling.
