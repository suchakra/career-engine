"""CareerEngine integration layer — wires the CLI entry point to the ADK workflow.

This package is the ONLY place where:
- The real google.genai model client is instantiated.
- Auth (CliAuthProvider) and key vault (SecretManagerKeyVault) are wired together.
- Access-mode resolution maps a user to FREE or BYOK.
- The ADK Runner + session service are assembled.

It has zero UI imports; a Streamlit or other web frontend can reuse all of
this by importing from here rather than duplicating the wiring.
"""
