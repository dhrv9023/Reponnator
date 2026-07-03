# CodeAutopsy × Repponator — Website UI/UX Specification

This document details the visual layouts, interactive components, pages, and architectural sections required to build a premium, state-of-the-art web interface for the **CodeAutopsy × Repponator** system. 

It acts as a complete blueprint for the design and frontend engineering teams when building the visual layer on top of our Phase 1 & 2 backend intelligence.

---

## 🎨 Design Philosophy & Visual Language

To create a state-of-the-art, "wow-factor" experience, the website should employ modern, premium UI/UX aesthetics:

*   **Color Palette:**Harmonious dark-mode system tailored for developer tools (sleek deep space greys, muted slate backgrounds, neon/cyberpunk glowing accent colors for data representations: e.g., cyan/blue for normal imports, emerald green for entry points, violet for circular dependencies).
*   **Aesthetics:** Subtle glassmorphism (`backdrop-filter: blur`), smooth gradients, dynamic shadows, and clean modern typography (e.g., *Outfit* for headers, *Inter* or *Geist* for body, and *Framer Mono* or *JetBrains Mono* for code panels).
*   **Transitions & Micro-animations:** Butter-smooth hover states, fading overlays, spring-based sliding panels, and pulsating halo effects on interactive diagrams.

---

## 🗺️ Page 1: The Ingestion Console (Landing Page)

This is the entry point where developers input their public GitHub repositories.

```
┌────────────────────────────────────────────────────────┐
│  🌌 CODEAUTOPSY × REPPONATOR                           │
│                                                        │
│       Decode Any Codebase in Seconds                   │
│       [ Enter public GitHub Repository URL...       ]  │
│       [ Branch: main ▼ ]  [ 🚀 Decode Codebase ]      │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │ ⚡ Active Process Log (WebSocket / SSE Stream)   │  │
│  │ 📂 Fetching: 15/15 files [██████████] 100%       │  │
│  │ 🔬 Parsing: 119 functions, 29 classes found      │  │
│  │ 🔗 Building Call Graph... [OK]                    │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  📂 Previously Explored Repositories                   │
│  📁 pallets/itsdangerous     📁 pallets/flask          │
└────────────────────────────────────────────────────────┘
```

### Key Sections & Features:
1.  **The Hero Spotlight:** A bold, striking central headline declaring the application's capabilities, surrounded by a subtle, glowing particle background.
2.  **The Ingestion Bar:**
    *   A clean, prominent input field with automatic URL validation (supporting copy-pasting of full GitHub URLs or quick-typing of `owner/repo`).
    *   Advanced option dropdown to specify a target branch/commit hash (defaulting to the primary branch).
3.  **The Live Action Dashboard (WebSocket/SSE Monitor):**
    *   Instead of a static loading spinner, show a terminal-like log dashboard that streams exact execution phases from our backend.
    *   Phases displayed: *Ingesting files* (Phase 1) → *AST Parsing* (Phase 2) → *Generating Graphs* (Phase 2) → *Vector Indexing* (Phase 3) → *Story Weaver* (Phase 5).
4.  **Recent Files/History Grid:**
    *   Displays cards for previously ingested repositories stored in local cache.
    *   Shows repository stats (Primary Language, File count, last parsed date) with single-click reload.

---

## 🗺️ Page 2: The Main Workspace (The Dashboard)

Once a repository has been processed, the user is redirected to a multi-pane, immersive dashboard.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ 📁 pallets/itsdangerous 🟢 parsed  [Search functions, classes...]          │
├──────────────────────┬───────────────────────────────┬─────────────────────┤
│ 📖 THE NARRATIVE     │ 🕸️ CODEAUTOPSY DIAGRAM        │ 💬 ARCHITECT Q&A    │
│                      │                               │                     │
│ 1. Core Architecture │        [UserService]          │ > How does token    │
│                      │          /       \            │   validation work?  │
│ This library handles │    [Parser]    [Hasher]       │                     │
│ cryptographic values │        \       /              │ Based on the        │
│ safely. The main     │       [UserHelper]            │ call graph, the     │
│ utility class is...  │                               │ `Serializer` calls  │
│                      │   [🔎 Zoom In] [⚙️ Call Graph] │ `load()` here:      │
│ 2. Design Decisions  │                               │ ┌─────────────────┐ │
│                      │ Node Inspector Panel:         │ │ load(self, ...) │ │
│ 🔸 Why choice X?     │ Class: UserService            │ └─────────────────┘ │
│ 🔸 Security Tradeoff │ Lines: 45 - 120               │ [Ask anything...]   │
└──────────────────────┴───────────────────────────────┴─────────────────────┘
```

The workspace is divided into three highly functional, resizable columns:

### 1. Left Panel: The Architectural Narrative (Repponator)
*   **The Storyteller Interface:** Displays the prose explaining *why* the codebase is designed the way it is. Uses Markdown rendering with beautiful margins, clean quote-blocks, and structural headings.
*   **Key Design Highlights:** Lists major architectural trade-offs, pattern alerts (e.g., MVC, Layered), and directory structures.
*   **Hover-to-Highlight Code Linking:** Hovering over a code snippet or function name in the narrative dynamically highlights that specific node/connection in the center diagram, creating a deep cognitive connection.

### 2. Center Panel: The Interactive Architecture Diagram (CodeAutopsy)
*   **The Canvas:** An interactive, zoomable, pannable visualization canvas using **React Flow**, **Cytoscape.js**, or **D3.js**.
*   **Visualization Modes:**
    *   *Mode A: File Dependency Graph:* Shows how files import each other. Highlights circular dependencies in neon red.
    *   *Mode B: Function Call Graph:* Shows how functions call each other. Core utility functions (highest in-degree) are represented by larger nodes. Entry points glow.
*   **Dynamic Search & Filtering:** An overlay search bar allows users to search for a function, class, or variable name. The canvas instantly zooms and highlights the target node.
*   **Inspect Drawer (Node Inspector):** Clicking on any node slides out a detailed side-inspector displaying:
    *   Parameters and return types.
    *   Calculated complexity score with a colored gauge (Green = Simple, Red = Complex).
    *   Docstring and a preview of the source code.
    *   List of other functions calling it, and functions it calls.

### 3. Right Panel: Grounded Agentic Q&A Chat
*   **The Assistant Window:** A persistent chat window styled like a high-end chat workspace (e.g., ChatGPT/Claude) dedicated to answering questions about the codebase.
*   **Source Citation Overlay:** Every answer generated by the agent must include clickable, grounded code references.
*   **Inspect Code Overlay:** Clicking a source reference pops up a sliding code block overlay showing the exact file lines in context (with full syntax highlighting), without forcing the user to leave the workspace.

---

## 🛠️ Recommended Frontend Tech Stack

To ensure optimal performance (especially when rendering large interactive node diagrams) and smooth interactivity, the frontend should use:

*   **Framework:** **Next.js** (React) for rich routing, server-side landing rendering, and quick API endpoints.
*   **State Management:** **Zustand** or **Redux Toolkit** to easily sync selected nodes, active highlighted paths, and chat history.
*   **Styling & Components:** **Tailwind CSS** or Vanilla CSS variables to control theme configurations easily.
*   **Visualization Canvas:**
    *   **React Flow** (best for modular, customizable, and node-based UI structures).
    *   **D3.js** (best for highly optimized force-directed graph layouts in large codebases).
*   **Interactivity:** **Framer Motion** for spring-based UI animations, card slides, and smooth panel expansions.
*   **Code Highlighting:** **Shiki** or **Prism.js** for high-quality syntax highlighting of multiple code languages.

---

## 📈 Next Steps (When You Are Ready to Build)
When the user directs the agent to begin website development, the workflow will be:
1.  Initialize the Next.js/React framework in the workspace root.
2.  Set up the global state variables to structure inputs, parsing logs, diagram selections, and chat messages.
3.  Implement the landing page with interactive terminal output.
4.  Build the canvas and node inspector panels.
5.  Link the Python backend pipelines to supply live websocket outputs.
