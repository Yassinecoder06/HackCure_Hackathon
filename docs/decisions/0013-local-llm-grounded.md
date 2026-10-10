# 0013. Optional local LLM layer: grounded on structured facts, verified, never on alerts

Status: accepted (2026-10-10). Moves the "local LLM" item from Won't to **Could** (after the FHIR export, the template explainer and P4).

## Context

Every algorithmic output already carries template explanations built from the rule that fired (HackCure section 6, [ADR 0011](0011-interop-and-confidence.md)). We want readable shift-handover summaries and free-text questions ("why is B06 first?") too. A small local language model can phrase those, but it can also get a number wrong or invent a cause. In a clinical tool that is worse than no answer.

## Decision

**1. Templates stay the source of truth.** Alert, NEWS2 and suggestion explanations remain deterministic templates. The LLM never writes them, never sits on the triage path (latency budget under 1 s), and the system works fully without it.

**2. The LLM only rephrases or answers from facts we select. This is structured retrieval, not classic RAG, for ward data.** Live ward facts are exact, structured and small, so a lookup beats similarity search, which could pull the wrong bed or an old reading.

```
question → 1. intent router (deterministic): bed_status · why_ranked · changes_since · handover_summary · ward_summary
         → 2. fact builder (deterministic, from the twin + event log): numbered facts [f1] [f2] …
         → 3. local LLM, temperature 0, instructed to use ONLY these facts and cite them
         → 4. verifier (deterministic): every number, bed id, time and citation must match a fact,
              otherwise the answer is discarded and the template text is shown instead
         → 5. labelled "AI summary: check source data", audited
```

- **We choose the facts, not the model.** Small models are unreliable at choosing tools, so a deterministic router handles a fixed set of intents. Anything else gets "I can only answer questions about the ward's current state."
- **It abstains** when the facts don't cover the question.
- **No diagnosis, no treatment advice, no reassurance text for families.** It never appears on alerts or in the Family Care Link (safety invariant 2).
- **It is measured:** a CI test set of questions with the expected facts reports the verifier's rejection rate (the hallucination rate).

**3. Document RAG only for real documents, later.** Protocols and guidelines (NEWS2 response guidance, ward procedures) are unstructured text, which is what RAG is for. A small multilingual embedding model with a local index over **approved documents only**; answers quote and cite the passage and are labelled as protocol text, not advice. This needs real hospital documents first.

**4. Runtime.** An `llm` service in the inference layer ([ADR 0009](0009-layers-and-postgres.md)) running a small open instruct model (3–4 billion parameters, quantised to about 2–3 GB) through Ollama.
- It fits the RTX 4060 (8 GB); without a GPU it runs on the CPU, which is slow but acceptable because nothing urgent waits on it.
- **Local only:** no patient data goes to a cloud API (INPDP, privacy by design).
- Two or three candidate models are compared on French output before choosing. Small models are weaker in Arabic, especially Tunisian Arabic.

## Consequences

- B owns the router, fact builder, verifier and evaluation set. A adds the `llm` service to compose as an optional profile, so the default demo stack doesn't depend on it.
- The pitch can say "AI where it is safe": deterministic scoring and explanations, plus a grounded, verified, local language layer for summaries.
