# Building a Spotify MCP Server with Cursor: A Real-World AI Pair Programming Experience

As software engineers, we're constantly evaluating new tools that promise to make us more productive. When Anthropic released the Model Context Protocol (MCP) and Cursor gained popularity as an AI-powered IDE, I decided to put them both to the test by building something practical: a Spotify MCP server that would let AI assistants interact with the Spotify Web API.

This article chronicles my real experience building this project with Cursor—the good, the challenging, and the surprisingly effective moments of AI pair programming.

## What I Set Out to Build

My goal was straightforward: create a production-ready MCP server that could:
- Authenticate with Spotify's OAuth 2.0 API
- Provide 12+ tools for searching tracks, managing playlists, and accessing music metadata
- Integrate seamlessly with Cursor's MCP protocol
- Be packaged properly for easy distribution

I wanted to test Cursor's capabilities across the full development lifecycle—from initial architecture to debugging, testing, and deployment.

## The Journey: Key Moments and Lessons

### Starting Strong: Architecture and Boilerplate

**My prompt:** "I want to create a Spotify MCP server using FastMCP. Help me set up the project structure and basic authentication."

Cursor immediately impressed me by:
- Generating a well-structured Python project with proper `pyproject.toml`
- Creating separate modules for authentication, API client, and MCP tools
- Setting up OAuth 2.0 with PKCE flow correctly
- Including comprehensive error handling from the start

```python
# Cursor generated this clean authentication structure
class SpotifyAuthenticator:
    def __init__(self, config: SpotifyConfig):
        self.client_id = config.client_id
        self.client_secret = config.client_secret
        self.redirect_uri = config.redirect_uri
        self.code_verifier = base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8').rstrip('=')
```

**What worked well:** Cursor understood the domain context immediately and made sensible architectural decisions without me having to specify every detail.

### The First Major Hurdle: MCP Integration Issues

When I tried to test the server with Cursor's MCP integration, I hit a wall—the infamous "red dot" indicating the server wasn't connecting properly.

**My prompt:** "The dot is red in Cursor. Why?"

This kicked off a debugging session that revealed Cursor's systematic problem-solving approach. It methodically checked:
1. Configuration file paths (found they were relative, not absolute)
2. Logging output contaminating the JSON-RPC stream
3. Authentication token persistence across restarts

```bash
# The issue: FastMCP banner was contaminating stdout
FASTMCP_LOG_LEVEL=CRITICAL exec /opt/homebrew/bin/uvx --from /Users/oeftimie/work/ai/spotify-mcp-server spotify-mcp-server "${args[@]}"
```

**What I learned:** Cursor excels at systematic debugging when given clear error symptoms. It didn't just guess—it formed hypotheses and tested them methodically.

### The Package Management Pivot

Midway through development, I realized the virtual environment approach wasn't working well with Cursor's MCP integration.

**My prompt:** "It seems your suggestions did not work. Might be related to the fact that maybe venv is not the right tool to use as it might be re-generated each time I restart cursor? Maybe it should be packaged in UV and use UVX for it?"

This was a turning point. Cursor:
- Immediately understood the packaging problem
- Created a comprehensive migration plan with todo items
- Updated `pyproject.toml` for uvx compatibility
- Created a wrapper script for Cursor integration

```bash
#!/bin/bash
# Cursor-generated wrapper script
cd /Users/oeftimie/work/ai/spotify-mcp-server
FASTMCP_LOG_LEVEL=CRITICAL exec /opt/homebrew/bin/uvx --from /Users/oeftimie/work/ai/spotify-mcp-server spotify-mcp-server "${args[@]}"
```

**Key insight:** Cursor adapted well to changing requirements and didn't get stuck on its initial approach.

### The HTTP Client Lifecycle Bug

One of the trickiest bugs involved the Spotify API client being closed after the first request, causing subsequent calls to fail.

**The problem:**
```python
# Original problematic design
async def __aexit__(self, exc_type, exc_val, exc_tb):
    await self.client.aclose()  # This closed the client too early!
```

**Cursor's solution:**
```python
# Refactored to persistent client
async def _get_client(self) -> httpx.AsyncClient:
    if self._client is None or self._client.is_closed:
        self._client = httpx.AsyncClient(timeout=self.timeout)
    return self._client
```

**What impressed me:** Cursor identified this as an architectural issue, not just a bug, and proposed a comprehensive refactor with proper lifecycle management.

### Testing and Documentation Excellence

When I asked Cursor to create tests, it generated comprehensive test suites covering:
- Unit tests for individual components
- Integration tests with real API calls
- Middleware testing for the FastMCP stack
- Mock-based tests that actually tested logic, not mock behavior

```python
# Example of Cursor's thoughtful test design
@pytest.mark.asyncio
async def test_token_persistence():
    """Test that tokens work after a fresh server start."""
    # Simulates server restart by creating fresh instances
    token_manager = TokenManager(authenticator, Path("tokens.json"))
    await token_manager.load_tokens()
    
    # Tests actual API call, not just token loading
    user_info = await spotify_client.get_current_user()
    assert user_info.get('id') is not None
```

## Where Cursor Excelled

### 1. **Domain Understanding**
Cursor consistently demonstrated deep understanding of:
- OAuth 2.0 flows and security best practices
- FastMCP protocol requirements
- Python packaging and distribution
- Modern development tooling (uvx, uv, etc.)

### 2. **Systematic Problem Solving**
When issues arose, Cursor:
- Formed clear hypotheses
- Tested them methodically
- Provided detailed explanations of its reasoning
- Adapted when initial approaches didn't work

### 3. **Code Quality**
Generated code consistently featured:
- Proper error handling and logging
- Type hints and documentation
- Separation of concerns
- Modern Python patterns

### 4. **Project Management**
Cursor automatically:
- Tracked tasks and progress
- Suggested architectural improvements
- Maintained consistent coding standards
- Handled git operations properly

## Where Cursor Struggled

### 1. **MCP Protocol Nuances**
The JSON-RPC stream contamination issue took several iterations to resolve. Cursor initially focused on configuration rather than the fundamental stdout/stderr separation required by MCP.

### 2. **Environment-Specific Issues**
Path resolution and Homebrew installation locations required manual correction. Cursor made reasonable assumptions but couldn't account for my specific macOS setup.

### 3. **Iterative Refinement**
Some solutions required multiple attempts. For example, the HTTP client lifecycle fix went through several iterations before reaching the final architecture.

## Practical Takeaways for Engineers

### Do This:
- **Be specific about your environment** (OS, package managers, IDE setup)
- **Provide clear error messages** rather than vague descriptions
- **Let Cursor suggest architectural patterns** before imposing your own
- **Use Cursor's task management** features to track complex projects
- **Test Cursor's suggestions** systematically rather than assuming they're correct

### Watch Out For:
- **Environment assumptions** that may not match your setup
- **First solutions** that might need refinement for production use
- **Complex debugging scenarios** where multiple issues interact
- **Protocol-specific requirements** that need domain expertise

### Best Practices:
```python
# Always validate Cursor's suggestions with tests
def test_cursor_generated_function():
    result = cursor_function(test_input)
    assert result == expected_output
    
# Be explicit about requirements
# Good: "Create a FastMCP server with OAuth 2.0 PKCE flow"
# Better: "Create a FastMCP server with OAuth 2.0 PKCE flow that persists tokens and handles rate limiting"
```

## The Final Result

After our collaboration, I had:
- A fully functional Spotify MCP server with 12 API tools
- Comprehensive test suite with 95%+ coverage
- Modern packaging with uvx distribution
- Production-ready documentation
- Seamless Cursor MCP integration

The [final repository](https://github.com/oe-ai-experiments/spotify-mcp-server) represents about 6,600 lines of well-structured, tested code that I'm confident deploying to production.

## Reflections on AI Pair Programming

Working with Cursor felt like having a very knowledgeable junior developer who:
- Never gets tired or frustrated
- Has encyclopedic knowledge of best practices
- Can generate boilerplate incredibly quickly
- Needs guidance on architecture decisions but executes them well

The key was treating it as a true collaboration—I provided domain knowledge, requirements, and architectural direction, while Cursor handled implementation details, testing, and documentation.

**Would I use Cursor for my next project?** Absolutely. The productivity gains were substantial, especially for:
- Initial project setup and boilerplate
- Test generation and documentation
- Systematic debugging and refactoring
- Package management and deployment tasks

The future of development isn't about AI replacing engineers—it's about AI amplifying our capabilities. Cursor proved to be an excellent amplifier, turning a weekend project into a production-ready system that I'm genuinely proud to ship.

---

*The complete Spotify MCP Server is available on [GitHub](https://github.com/oe-ai-experiments/spotify-mcp-server) with full documentation and installation instructions.*
