"""Smol Machines local and cloud VM workspace provider."""

from pydantic_ai_harness.smol_sandbox._backend import SmolSandboxBackend
from pydantic_ai_harness.smol_sandbox._capability import SmolSandbox

__all__ = ('SmolSandbox', 'SmolSandboxBackend')
