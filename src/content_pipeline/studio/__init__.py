"""Studio: the chat-driven, agentic short-form video editor.

A reference implementation of the architecture described in docs/studio/:
  - a persistent media memory (analyze once, query forever),
  - swappable skills behind typed contracts (mock now, hosted/self-host later),
  - perception/director/critic agents over a shared blackboard,
  - role-based handling of asymmetric clips (great-visual / great-audio),
  - an event bus that drives the live dashboard.

Nothing here is locked to a vendor: every capability is an adapter. The
mock/heuristic adapters let the whole pipeline run end-to-end with zero
network and zero ML weights, so you can validate edit quality first and
swap real models in one at a time.
"""
