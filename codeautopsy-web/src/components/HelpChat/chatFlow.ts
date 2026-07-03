export interface FlowOption {
  label: string;
  next?: string;
  emailSubject?: string;
}

export interface FlowNode {
  id: string;
  message: string;
  options: FlowOption[];
  isEmailGateway?: boolean;
}

export const FLOW: Record<string, FlowNode> = {
  // ── ROOT ───────────────────────────────────────────────
  root: {
    id: "root",
    message: "Hey! 👋 I'm here to help with CodeAutopsy.\nWhat brings you here today?",
    options: [
      { label: "🤖 Ask AI Support",        next: "ask_ai" },
      { label: "🚀 Getting started",       next: "getting_started" },
      { label: "⚙️  Technical issues",     next: "technical_issues" },
      { label: "📊 Understanding output",  next: "understanding_output" },
      { label: "✉️  Contact / Other",       next: "other" }
    ]
  },

  ask_ai: {
    id: "ask_ai",
    message: "I am ready! Ask me anything about the CodeAutopsy project, its tech stack, how it was made, its visualization system, or the completed phases.",
    options: []
  },

  // ── GETTING STARTED ────────────────────────────────────
  getting_started: {
    id: "getting_started",
    message: "Great! What would you like help with?",
    options: [
      { label: "How do I analyze a repo?",        next: "how_to_analyze" },
      { label: "Which languages are supported?",  next: "languages" },
      { label: "What does each phase do?",        next: "phases_overview" },
      { label: "Something else",                  next: "other" }
    ]
  },

  how_to_analyze: {
    id: "how_to_analyze",
    message: "To analyze a repo:\n1. Paste any public GitHub URL\n2. Click Analyze\n3. Wait for all 3 phases to complete\n\nPhases take 1-3 mins depending on repo size.\n\nDid this help?",
    options: [
      { label: "Yes, got it! ✅",      next: "resolved" },
      { label: "I'm getting an error", next: "technical_issues" },
      { label: "Tell me more",         next: "phases_overview" },
      { label: "Contact support",      next: "other" }
    ]
  },

  languages: {
    id: "languages",
    message: "CodeAutopsy currently supports:\n\n🐍 Python  ⚡ JavaScript  📘 TypeScript\n☕ Java  🐹 Go  🦀 Rust  ⚙️ C/C++\n\nMore languages coming soon!\n\nIs your repo in one of these?",
    options: [
      { label: "Yes, it is ✅",                  next: "resolved" },
      { label: "No, my language isn't listed",   next: "language_request" },
      { label: "Mixed languages — will it work?", next: "mixed_languages" },
      { label: "Back",                            next: "getting_started" }
    ]
  },

  language_request: {
    id: "language_request",
    message: "We're actively adding more languages! Want to request support for a specific language? Our team will prioritize based on demand.",
    options: [
      { label: "Yes, request a language ✉️",  next: "other" },
      { label: "Just browsing for now",       next: "resolved" },
      { label: "Back",                        next: "languages" }
    ]
  },

  mixed_languages: {
    id: "mixed_languages",
    message: "Yes! Mixed language repos work. CodeAutopsy detects each file's language automatically and applies the right parser. The architecture diagram will show cross-language dependencies too.\n\nDid that answer your question?",
    options: [
      { label: "Yes, perfect ✅",    next: "resolved" },
      { label: "Still have questions", next: "other" },
      { label: "Back",               next: "languages" }
    ]
  },

  phases_overview: {
    id: "phases_overview",
    message: "CodeAutopsy runs 3 phases:\n\n📥 Phase 1 — Fetches all code files\n🔍 Phase 2 — Parses structure & relationships\n🧠 Phase 3 — Embeds everything for AI search\n\nWhich phase would you like to know more about?",
    options: [
      { label: "Phase 1 — Fetching",  next: "phase1_detail" },
      { label: "Phase 2 — Parsing",   next: "phase2_detail" },
      { label: "Phase 3 — Embedding", next: "phase3_detail" },
      { label: "Back",                next: "getting_started" }
    ]
  },

  phase1_detail: {
    id: "phase1_detail",
    message: "Phase 1 fetches all code files from the GitHub repo using the GitHub API. It filters out node_modules, build artifacts, and binary files automatically. Only source code files are kept.\n\nAnything else?",
    options: [
      { label: "Tell me about Phase 2",  next: "phase2_detail" },
      { label: "I'm all good ✅",        next: "resolved" },
      { label: "Contact support",        next: "other" }
    ]
  },

  phase2_detail: {
    id: "phase2_detail",
    message: "Phase 2 uses Tree-sitter to parse every file into its structure — extracting functions, classes, imports, and call relationships. This builds the call graph and dependency map.\n\nAnything else?",
    options: [
      { label: "Tell me about Phase 3",  next: "phase3_detail" },
      { label: "I'm all good ✅",        next: "resolved" },
      { label: "Contact support",        next: "other" }
    ]
  },

  phase3_detail: {
    id: "phase3_detail",
    message: "Phase 3 chunks all the parsed code intelligently (by function/class), embeds each chunk using AI embeddings, and stores them in a vector database. This powers the Q&A and architecture story features.\n\nAnything else?",
    options: [
      { label: "I'm all good ✅",   next: "resolved" },
      { label: "Back to phases",    next: "phases_overview" },
      { label: "Contact support",   next: "other" }
    ]
  },

  // ── TECHNICAL ISSUES ───────────────────────────────────
  technical_issues: {
    id: "technical_issues",
    message: "Sorry to hear that! What kind of issue are you facing?",
    options: [
      { label: "Analysis is stuck / not completing", next: "analysis_stuck" },
      { label: "Diagram not rendering",             next: "diagram_issue" },
      { label: "Q&A giving wrong answers",          next: "qa_issue" },
      { label: "Something else",                    next: "other" }
    ]
  },

  analysis_stuck: {
    id: "analysis_stuck",
    message: "Analysis can sometimes take longer for large repos. Where is it stuck?",
    options: [
      { label: "Stuck on Phase 1 (Fetching)",   next: "stuck_phase1" },
      { label: "Stuck on Phase 2 (Parsing)",    next: "stuck_phase2" },
      { label: "Stuck on Phase 3 (Embedding)",  next: "stuck_phase3" },
      { label: "It just says Error",            next: "generic_error" }
    ]
  },

  stuck_phase1: {
    id: "stuck_phase1",
    message: "Phase 1 issues are usually caused by:\n\n• Private repo (needs auth token)\n• Invalid GitHub URL format\n• GitHub API rate limit hit\n\nIs your repo public?",
    options: [
      { label: "Yes it's public",      next: "stuck_phase1_public" },
      { label: "No it's private",      next: "private_repo" },
      { label: "Not sure",             next: "other" }
    ]
  },

  stuck_phase1_public: {
    id: "stuck_phase1_public",
    message: "Try these steps:\n1. Make sure URL format is: github.com/owner/repo\n2. Wait 2 minutes (GitHub rate limit resets)\n3. Try a different repo to test\n\nDid any of these fix it?",
    options: [
      { label: "Yes, fixed! ✅",         next: "resolved" },
      { label: "Still stuck",            next: "other" }
    ]
  },

  private_repo: {
    id: "private_repo",
    message: "Private repos require a GitHub Personal Access Token. Add your token in the Settings panel before analyzing.\n\nNeed help generating a GitHub token?",
    options: [
      { label: "Yes, how do I get a token?", next: "github_token" },
      { label: "Already added, still failing", next: "other" },
      { label: "Got it, thanks ✅",            next: "resolved" }
    ]
  },

  github_token: {
    id: "github_token",
    message: "To generate a GitHub token:\n1. Go to github.com → Settings\n2. Developer Settings → Personal Access Tokens\n3. Generate new token (classic)\n4. Select 'repo' scope\n5. Copy and paste into CodeAutopsy settings\n\nDid that help?",
    options: [
      { label: "Yes, working now ✅",  next: "resolved" },
      { label: "Still not working",   next: "other" }
    ]
  },

  stuck_phase2: {
    id: "stuck_phase2",
    message: "Phase 2 can be slow on repos with 500+ files or complex code. It should complete within 5 minutes.\n\nHow long have you been waiting?",
    options: [
      { label: "Less than 5 minutes",  next: "wait_phase2" },
      { label: "More than 5 minutes",  next: "other" },
      { label: "It errored out",       next: "generic_error" }
    ]
  },

  wait_phase2: {
    id: "wait_phase2",
    message: "Phase 2 is still within normal time. Large repos with complex class hierarchies can take up to 5 minutes. Keep the tab open and wait a bit more.\n\nDid it complete?",
    options: [
      { label: "Yes, it finished ✅",   next: "resolved" },
      { label: "Still stuck after 5min", next: "other" }
    ]
  },

  stuck_phase3: {
    id: "stuck_phase3",
    message: "Phase 3 (embedding) is the most compute-intensive step. For large repos it can take 3-5 minutes.\n\nHave you been waiting more than 5 minutes?",
    options: [
      { label: "No, I'll wait more",   next: "wait_phase3" },
      { label: "Yes, 5+ minutes",      next: "other" },
      { label: "It shows an error",    next: "generic_error" }
    ]
  },

  wait_phase3: {
    id: "wait_phase3",
    message: "Good — keep the tab open and don't refresh. Refreshing during Phase 3 will restart the embedding process.\n\nDid it complete?",
    options: [
      { label: "Yes! ✅",             next: "resolved" },
      { label: "Still stuck",         next: "other" }
    ]
  },

  generic_error: {
    id: "generic_error",
    message: "Sorry about that error! A few quick things to try:\n1. Refresh and try again\n2. Try with a smaller repo first\n3. Check if GitHub is down: githubstatus.com\n\nDid any of these help?",
    options: [
      { label: "Yes, fixed ✅",           next: "resolved" },
      { label: "No, still getting error", next: "other" }
    ]
  },

  diagram_issue: {
    id: "diagram_issue",
    message: "What's happening with the diagram?",
    options: [
      { label: "Blank / nothing showing",       next: "diagram_blank" },
      { label: "Diagram looks wrong/confusing", next: "diagram_confusing" },
      { label: "Can't interact with nodes",     next: "diagram_interaction" },
      { label: "Back",                          next: "technical_issues" }
    ]
  },

  diagram_blank: {
    id: "diagram_blank",
    message: "A blank diagram usually means:\n• Phase 3 didn't complete fully\n• Repo had no parseable code files\n• Browser rendering issue\n\nTry: Hard refresh (Ctrl+Shift+R / Cmd+Shift+R)\n\nDid that fix it?",
    options: [
      { label: "Yes ✅",          next: "resolved" },
      { label: "Still blank",     next: "other" }
    ]
  },

  diagram_confusing: {
    id: "diagram_confusing",
    message: "Very large repos can produce complex diagrams. You can:\n• Use the zoom controls\n• Click a node to focus on its connections\n• Use the search bar to find specific components\n• Switch to Story view for a narrative explanation\n\nDoes that help?",
    options: [
      { label: "Yes, much better ✅", next: "resolved" },
      { label: "Still confused",      next: "understanding_output" },
      { label: "Contact support",     next: "other" }
    ]
  },

  diagram_interaction: {
    id: "diagram_interaction",
    message: "Interaction issues are usually browser-specific. Try:\n• Chrome or Firefox (best support)\n• Disable browser extensions\n• Try incognito/private mode\n\nDid that help?",
    options: [
      { label: "Yes, working now ✅",  next: "resolved" },
      { label: "Still not working",   next: "other" }
    ]
  },

  qa_issue: {
    id: "qa_issue",
    message: "What's wrong with the Q&A answers?",
    options: [
      { label: "Answers seem made up",        next: "qa_hallucination" },
      { label: "Answers are too vague",       next: "qa_vague" },
      { label: "Wrong file/function cited",   next: "qa_wrong_citation" },
      { label: "Back",                        next: "technical_issues" }
    ]
  },

  qa_hallucination: {
    id: "qa_hallucination",
    message: "CodeAutopsy grounds all answers in your actual code. If answers seem off:\n• Ask more specific questions (include function/class names)\n• Ask about files you can see in the diagram\n• The Q&A works best with Phase 3 fully complete\n\nWas Phase 3 fully completed before asking?",
    options: [
      { label: "Yes it was complete",     next: "qa_specific" },
      { label: "Not sure",                next: "other" }
    ]
  },

  qa_specific: {
    id: "qa_specific",
    message: "Try asking very specific questions:\n✅ 'What does UserService.get_user() return?'\n✅ 'What does auth/middleware.py import?'\n❌ 'Explain the whole codebase' (too broad)\n\nSpecific questions get much better answers.\n\nDid that help?",
    options: [
      { label: "Yes, works now ✅",   next: "resolved" },
      { label: "Still not right",    next: "other" }
    ]
  },

  qa_vague: {
    id: "qa_vague",
    message: "Vague answers usually mean the retrieval didn't find highly specific context. Try:\n• Mention the exact function or file name\n• Ask one specific thing at a time\n• Use exact class/function names from the diagram\n\nDoes that help?",
    options: [
      { label: "Yes, better now ✅",  next: "resolved" },
      { label: "Still vague",        next: "other" }
    ]
  },

  qa_wrong_citation: {
    id: "qa_wrong_citation",
    message: "Wrong citations can happen on very large repos where similar code patterns appear in multiple files. This is a known limitation we're working on.\n\nWould you like to report this as a bug?",
    options: [
      { label: "Yes, report bug ✉️",  next: "other" },
      { label: "No, thanks",         next: "resolved" }
    ]
  },

  // ── UNDERSTANDING OUTPUT ───────────────────────────────
  understanding_output: {
    id: "understanding_output",
    message: "Which part of the output would you like help understanding?",
    options: [
      { label: "The architecture diagram",     next: "understand_diagram" },
      { label: "The architectural story",      next: "understand_story" },
      { label: "The Q&A feature",              next: "understand_qa" },
      { label: "Something else",               next: "other" }
    ]
  },

  understand_diagram: {
    id: "understand_diagram",
    message: "The architecture diagram shows:\n\n🟦 Blue boxes → Files/Modules\n🟢 Green boxes → Entry points\n→ Arrows → Function calls or imports\n\nClick any box to see its functions and design explanation.\n\nIs there something specific you're confused about?",
    options: [
      { label: "What do the colors mean?",    next: "diagram_colors" },
      { label: "What are the arrows?",        next: "diagram_arrows" },
      { label: "Got it, thanks ✅",           next: "resolved" },
      { label: "Still confused",             next: "other" }
    ]
  },

  diagram_colors: {
    id: "diagram_colors",
    message: "Color guide:\n🟢 Green → Entry point (where code starts)\n🟦 Blue → Regular module\n🟣 Purple → Core utility (called by many)\n🟠 Orange → External dependency\n⬜ Grey → Config/setup files\n\nDoes that help?",
    options: [
      { label: "Yes, clear now ✅",  next: "resolved" },
      { label: "More questions",    next: "understand_diagram" }
    ]
  },

  diagram_arrows: {
    id: "diagram_arrows",
    message: "Arrow guide:\n→ Solid arrow → direct function call\n⟶ Dashed arrow → import relationship\n↔ Double arrow → circular dependency (rare)\n\nThicker arrows = more frequent calls between modules.\n\nClear now?",
    options: [
      { label: "Yes ✅",            next: "resolved" },
      { label: "Still confused",   next: "other" }
    ]
  },

  understand_story: {
    id: "understand_story",
    message: "The Architectural Story (Repponator) explains:\n\n📖 WHY the repo is built the way it is\n🔗 How each design decision connects to others\n🏛️ The founding architectural commitment of the codebase\n\nIt's a narrative — meant to be read top to bottom like an article.\n\nAny specific part confusing?",
    options: [
      { label: "What is 'primary architectural commitment'?",
                                            next: "primary_commitment" },
      { label: "The story seems wrong",    next: "story_wrong" },
      { label: "Got it, thanks ✅",        next: "resolved" }
    ]
  },

  primary_commitment: {
    id: "primary_commitment",
    message: "The 'primary architectural commitment' is the single foundational design decision that all other decisions trace back to.\n\nExample: If a repo chose event-driven architecture early on, that single choice forced stateless auth, async processing, and a message queue — every other decision flowed from it.\n\nMake sense?",
    options: [
      { label: "Yes, that's clear ✅",  next: "resolved" },
      { label: "Not quite",            next: "other" }
    ]
  },

  story_wrong: {
    id: "story_wrong",
    message: "The story is AI-generated from your code's structure. It may occasionally misinterpret intent on:\n• Auto-generated code\n• Very small repos (< 10 files)\n• Repos with unusual structure\n\nIs your repo one of these?",
    options: [
      { label: "Yes, it's small/unusual",  next: "story_limitation" },
      { label: "No, it's a normal repo",   next: "other" }
    ]
  },

  story_limitation: {
    id: "story_limitation",
    message: "For small or unusual repos, the story may be less accurate. CodeAutopsy works best on repos with:\n• 20+ source files\n• Clear folder structure\n• Standard naming conventions\n\nThis is a known limitation. We're improving it!\n\nWant to report this case to help us improve?",
    options: [
      { label: "Yes, I'll report it ✉️",  next: "other" },
      { label: "No thanks",              next: "resolved" }
    ]
  },

  understand_qa: {
    id: "understand_qa",
    message: "The Q&A feature lets you ask anything about the codebase in plain English.\n\nBest practices:\n✅ Ask about specific functions or files\n✅ Ask 'why' and 'how' questions\n✅ Reference names you see in the diagram\n❌ Avoid questions needing external knowledge\n\nWant to try it now?",
    options: [
      { label: "Yes, I'll try it ✅",      next: "resolved" },
      { label: "It's not working well",   next: "qa_issue" },
      { label: "More questions",          next: "other" }
    ]
  },

  // ── RESOLVED ───────────────────────────────────────────
  resolved: {
    id: "resolved",
    message: "Glad I could help! 🎉\n\nIs there anything else you'd like to know?",
    options: [
      { label: "Ask another question",  next: "root" },
      { label: "Leave feedback ✉️",     next: "other" },
      { label: "No, all good! 👋",      next: "end" }
    ]
  },

  end: {
    id: "end",
    message: "Thanks for using CodeAutopsy! 🚀\n\nHappy exploring your codebase. Feel free to chat again anytime.",
    options: []   // empty = show "Start over" button only
  },

  // ── OTHER / EMAIL ──────────────────────────────────────
  other: {
    id: "other",
    message: "No problem! Send us a message and we'll get back to you.\n\nWhat's this about?",
    options: [
      { label: "🐛 Bug report",           emailSubject: "Bug Report" },
      { label: "💡 Feature request",      emailSubject: "Feature Request" },
      { label: "❓ General question",     emailSubject: "General Question" },
      { label: "🔑 Access / Account",     emailSubject: "Access Issue" }
    ],
    isEmailGateway: true   // signals to render EmailForm next
  }
};
