# Project Specification: AI-Powered Grocery Agent (LangGraph & MCP)

This specification defines a state-of-the-art **agentic workflow** using **LangGraph** to manage complex states and **MCP (Model Context Protocol)** to interface with services. This architecture moves away from rigid scripts toward a flexible, "human-in-the-loop" autonomous system.

---

## 1. Project Overview

A self-hosted AI agent that automates grocery planning and ordering. The system "thinks" in a graph-based workflow, fetching recipes from **Mealie**, checking a **Pantry Bypass** list, pausing for user verification, and finally executing orders via **Kroger**.

---

## 2. Technical Architecture

* **Orchestration Framework:** LangGraph (Python) for state management and cycles.
* **Protocol:** Model Context Protocol (MCP) for service abstraction.
* **Recipe Database:** Mealie (Docker) via `mealie-mcp-server`.
* **Grocery Provider:** Kroger via `kroger-mcp`.
* **Frontend:** Streamlit for a lightweight, interactive dashboard.
* **Deployment:** Docker Compose on a Linux/Arch environment.

---

## 3. The LangGraph Workflow (State Machine)

### Node 1: Recipe Extraction (`fetch_recipes`)

* **Input:** User text (e.g., "I want to make the Shrimp Scampi from Mealie").
* **Action:** Agent calls `mealie.get_recipe`.
* **State Update:** Stores raw ingredient JSON in the graph state.

### Node 2: Pantry Filtering (`filter_ingredients`)

* **Input:** Raw ingredient list.
* **Action:** Logic compares items against a configurable `pantry.yaml`.
* **State Update:** Moves matching items to a "Pantry" list and others to a "Pending Cart" list.

### Node 3: Human-in-the-Loop (`wait_for_approval`)

* **Input:** "Pending Cart" list.
* **Action:** The graph **interrupts** and waits.
* **Frontend Action:** Streamlit displays a checklist. The user unchecks anything they already have.
* **Transition:** Once the user clicks "Approve," the graph resumes.

### Node 4: Fulfillment (`execute_kroger_order`)

* **Input:** Confirmed ingredient list.
* **Action:** Agent calls `kroger.search_products` for each item and `kroger.add_items_to_cart`.
* **State Update:** Stores order confirmation and estimated total.

---

## 4. Discrete Task List

### Phase 1: Environment & MCP Config

* [ ] **1.1 Docker Networking:** Configure a dedicated Docker network so Mealie, MCP servers, and the Python Agent can communicate by hostname.
* [ ] **1.2 MCP Discovery:** Install `uv` and verify both `mealie-mcp-server` and `kroger-mcp` respond to `list_tools`.

### Phase 2: LangGraph Implementation

* [ ] **2.1 State Definition:** Define a TypedDict for the Graph State (recipes, ingredients, user_approvals, cart_status).
* [ ] **2.2 Logic Nodes:** Implement the Python functions for filtering and tool calling.
* [ ] **2.3 Interruption Logic:** Implement a `checkpointer` (SQLite) to allow the graph to pause and resume across Streamlit sessions.

### Phase 3: Frontend & Web Search

* [ ] **3.1 Streamlit Dashboard:** Build a two-column UI (Chat on left, Cart Status/Checklist on right).
* [ ] **3.2 Agentic Web Search:** Integrate a "Search Node" that uses an LLM to browse for recipes if they aren't found in Mealie, then offers to clip them.

---

## 5. Configuration (`pantry.yaml`)

```yaml
# Sane defaults for a backend developer's pantry
bypass_staples:
  - salt
  - black pepper
  - water
  - ice
  - olive oil
  - flour
  - baking soda
  - cornstarch

```
