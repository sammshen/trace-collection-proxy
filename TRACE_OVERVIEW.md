# Trace Overview

All traces were collected via the instrumented proxy (`instrumented_proxy.py`) against **MiniMaxAI/MiniMax-M2.5**.

Boot sequences (openclaw `/new`/`/reset` startup) have been stripped from task traces and collected into `boot_sequences_trace.jsonl`.

| Trace | User Requests | LLM Queries | Tool Use | Topic |
|-------|--------------|-------------|----------|-------|
| ai_fashion_industry | 1 | 34 | Yes | AI fashion industry research |
| deepseek_sentiment | 1 | 16 | Yes | Sentiment analysis |
| estimate_clinical_population | 1 | 18 | Yes | Clinical population estimation |
| financial_analysis | 1 | 11 | Yes | Financial analysis |
| interview_schedule | 1 | 14 | Yes | Interview scheduling |
| japan_trip | 1 | 3 | Yes | Japan trip planning |
| nyc_house | 1 | 8 | Yes | NYC house search |
| openclaw_llm_research | 1 | 6 | Yes | LLM research |
| price_optimization | 1 | 19 | Yes | Price optimization |
| tech_consulting | 1 | 8 | Yes | Tech consulting |
| yc_search | 1 | 30 | Yes | YC company search |
| boot_sequences | 0 | 7 | Yes | Openclaw startup sequences |

**Totals:** 11 user requests, 174 LLM queries, 12 traces