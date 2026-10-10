# Smol Sandbox

Run an agent's commands and file edits in an isolated [Smol Machines](https://github.com/smol-machines/smol) microVM, locally or on Smol Cloud.

[Source](https://github.com/pydantic/pydantic-ai/tree/main/src/pydantic_ai_harness/pydantic_ai_harness/smol_sandbox/)

> While Pydantic AI Harness is on 0.x releases, the API may change between minor releases; when it does, deprecation warnings and release-note migration guidance tell you (or your agent) exactly how to upgrade. See the [version policy](https://pydantic.dev/docs/ai/harness/#version-policy).

## Install

uv:

```bash
uv add "pydantic-ai-harness[smol,anthropic]"
```

pip:

```bash
pip install "pydantic-ai-harness[smol,anthropic]"
```

The Anthropic extra supplies the model in the example. The `smol` extra installs the VM engine on Linux x86_64/aarch64 (glibc 2.34 or later) and macOS arm64. A local VM also needs KVM or macOS Hypervisor.framework. Smol Cloud uses the same SDK and needs `SMOL_CLOUD_TOKEN` instead of a local hypervisor; the SDK currently has no Windows wheel, even for its cloud transport.

## Quick start

```python {names="defined"}
from pydantic_ai import Agent
from pydantic_ai_harness.filesystem import FileSystem
from pydantic_ai_harness.shell import Shell
from pydantic_ai_harness.smol_sandbox import SmolSandbox

agent = Agent('anthropic:claude-opus-5-5', capabilities=[SmolSandbox(), Shell(), FileSystem()])
result = agent.run_sync('Write hello.txt and print its contents.')
```

A new run creates a VM when it first uses its workspace. `FileSystem` and `Shell` share that VM; the host's files and shell remain separate. New VMs have outbound networking disabled by default; use `SmolSandbox(network=True)` when the guest must download packages or repositories. The default Alpine image supplies `sh` and the BusyBox utilities used by the workspace's file operations. Custom images need `sh`, `base64`, `cp`, `dd`, `find`, `mkdir`, `mv`, `readlink`, `rm`, and `wc`.

For coding agents, add `Coder(repo_context=False)` and install `git` and `ripgrep` in the VM. `RepoContext` otherwise attempts to inspect a repository before the run's first tool call.

## Reuse and cleanup

Save `result.workspace.ref` and pass it back through `workspace=` on the next run, or pass the previous run's `message_history`. Local VMs remain persistent so their references can be reattached across processes. If the referenced VM has been deleted, the run raises `WorkspaceUnavailableError`; it does not create a different VM.

```python {names="defined"}
from pydantic_ai import Agent
from pydantic_ai.workspaces import WorkspaceRef
from pydantic_ai_harness.filesystem import FileSystem
from pydantic_ai_harness.shell import Shell
from pydantic_ai_harness.smol_sandbox import SmolSandbox

sandbox = SmolSandbox()
agent = Agent('anthropic:claude-opus-5-5', capabilities=[sandbox, Shell(), FileSystem()])
result = agent.run_sync('Write hello.txt.')
ref: WorkspaceRef | None = result.workspace.ref
if ref is not None:
    later = agent.run_sync('Read hello.txt.', workspace=ref)
```

A run does not delete its VM. The local SDK can briefly start a stopped VM when attaching to delete it. Call `await sandbox.destroy(ref)` when it is no longer needed. Newly created cloud VMs also have a one-hour `ttl_seconds` default that deletes them if the application loses the reference; set a longer TTL if you need to reconnect later. Local VMs have no TTL. The reference contains only identity: reconnecting to a cloud VM still needs `SMOL_CLOUD_TOKEN` or `api_key=`.

A failed run has no result containing the ref. Build the backend yourself if you need cleanup on failure:

```python {names="defined"}
from pydantic_ai import Agent
from pydantic_ai_harness.filesystem import FileSystem
from pydantic_ai_harness.smol_sandbox import SmolSandbox, SmolSandboxBackend

backend = SmolSandboxBackend(target='cloud')
agent = Agent('anthropic:claude-opus-5-5', capabilities=[FileSystem()])
try:
    result = agent.run_sync('Write hello.txt.', workspace=backend)
finally:
    if backend.ref is not None:
        import asyncio

        asyncio.run(SmolSandbox(target='cloud').destroy(backend.ref))
```

In an existing async application, `await` the run and deletion instead of calling `asyncio.run`. A cancellation while the SDK creates a VM leaves the backend's acquisition task running until it records the ref. If the process exits before the SDK returns an ID, inspect the provider for an orphaned VM.

## Commands and output

`SmolSandbox(target='cloud')` switches from local to Smol Cloud without changing the `Shell` or `FileSystem` tools. `image`, `working_dir`, and `env` configure a new VM; `working_dir` and `env` also apply when attaching. The working directory must exist in an attached VM. The SDK requires asyncio; Trio is not supported.

Commands start with stdin at EOF. A nonzero exit is returned as a `CommandResult`. On timeout or cancellation, closing the stream kills local foreground work; in Cloud, closing the connection may leave the guest command running. A cloud command with a deadline also has a guest-enforced timeout at most one second later. For cancelled cloud commands without a deadline, inspect the VM or delete it if the command must stop. Detached background processes may continue. More than 10 MiB of combined output stops the stream and raises `WorkspaceOutputLimitError`; redirect larger output to a file. The streaming endpoint avoids Smol Cloud's 1 MiB cap on buffered text output. Invalid UTF-8 command bytes are replaced in text output.

The backend relies on Pydantic AI's shell filesystem fallback, which stages writes before renaming them. It uses more guest commands than Smol's native file API, especially for large files. The backend does not emit its own OpenTelemetry spans; the model and tool spans already cover agent operations, while Smol SDK lifecycle events do not yet expose timing and resource usage through this capability.
