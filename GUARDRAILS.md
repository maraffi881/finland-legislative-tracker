# System Guardrails

## Strict URL Generation Rule
The agent must never allow the Large Language Model (LLM) to generate, guess, or output source URLs. 

### Implementation Guardrail
- All ground-truth URLs (e.g., links to documents, PDFs, or web pages on Eduskunta or Finlex) must be constructed **deterministically** via Python code or templates using the official API IDs.
- Do not let the LLM attempt to predict or complete URL paths or query strings directly.
