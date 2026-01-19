# Project Tasks

## 4. Discrete Task List

### Phase 1: Environment & MCP Config

* [x] **1.1 Docker Networking:** Configure a dedicated Docker network so Mealie, MCP servers, and the Python Agent can communicate by hostname.
* [x] **1.2 MCP Discovery:** Install `uv` and verify both `mealie-mcp-server` and `kroger-mcp` respond to `list_tools`.

### Phase 2: LangGraph Implementation

* [ ] **2.1 State Definition:** Define a TypedDict for the Graph State (recipes, ingredients, user_approvals, cart_status).
* [ ] **2.2 Logic Nodes:** Implement the Python functions for filtering and tool calling.
* [ ] **2.3 Interruption Logic:** Implement a `checkpointer` (SQLite) to allow the graph to pause and resume across Streamlit sessions.

### Phase 3: Frontend & Web Search

* [ ] **3.1 Streamlit Dashboard:** Build a two-column UI (Chat on left, Cart Status/Checklist on right).
* [ ] **3.2 Agentic Web Search:** Integrate a "Search Node" that uses an LLM to browse for recipes if they aren't found in Mealie, then offers to clip them.
