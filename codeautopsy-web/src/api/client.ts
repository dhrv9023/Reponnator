/**
 * api/client.ts — REST API client for FastAPI backend integration
 * 
 * Phase 8: Connects React frontend directly to FastAPI REST gateway.
 */

const API_BASE = "http://localhost:8000/api";

export interface JobResponse {
  job_id: string;
  status: string;
  repo_key: string;
}

export interface JobStatusResponse {
  job_id: string;
  phase: string;
  repo_key: string;
  status: string;
  progress_percent: number;
  current_step: string | null;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
}

export interface RepoSummary {
  repo_key: string;
  owner: string;
  name: string;
  total_files: number;
  primary_language: string;
  ingested_at: string;
  phases_complete: string[];
}

export interface RepoDetailResponse {
  repo_key: string;
  owner: string;
  name: string;
  branch: string;
  total_files: number;
  total_bytes: number;
  primary_language: string;
  languages: Record<string, number>;
  ingested_at: string;
  phases_complete: string[];
}

export interface ParseResponse {
  repo_key: string;
  total_functions: number;
  total_classes: number;
  call_edges: number;
  detected_patterns: string[];
  entry_points: string[];
  parse_duration_seconds: number;
  files_parsed: number;
  files_failed: number;
}

export interface NodeMetadata {
  id: string;
  label: string;
  type: "entry_point" | "core_utility" | "module";
  functions: string[];
  classes: string[];
  call_count: number;
}

export interface DiagramResponse {
  mermaid_syntax: string;
  node_count: number;
  edge_count: number;
  metadata: NodeMetadata[];
}

export interface KeyModule {
  module_id: string;
  role_title: string;
  explanation: string;
}

export interface StoryResponse {
  project_summary?: string;
  tech_stack?: string[];
  primary_commitment: string;
  origin_story: string;
  how_it_flows: string;
  key_modules: KeyModule[];
  design_tensions: string;
  founding_metaphor: string;
  verdict: string;
  model_used: string;
  generation_duration_seconds: number;
  tokens_used: number;
}

export interface Citation {
  filename: string;
  line_start: number | null;
  line_end: number | null;
  snippet: string | null;
}

export interface QAResponse {
  answer: string;
  citations: Citation[];
  session_id: string;
  tokens_used: number;
  confidence: "high" | "medium" | "low";
}

export const apiClient = {
  // Phase 1: Ingestion
  ingestRepo: async (githubUrl: string, force = false): Promise<JobResponse> => {
    const res = await fetch(`${API_BASE}/repos/ingest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ github_url: githubUrl, force }),
    });
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return res.json();
  },

  listRepos: async (): Promise<{ repos: RepoSummary[] }> => {
    const res = await fetch(`${API_BASE}/repos`);
    if (!res.ok) throw new Error("Failed to fetch repositories.");
    return res.json();
  },

  getRepoDetail: async (repoKey: string): Promise<RepoDetailResponse> => {
    const res = await fetch(`${API_BASE}/repos/${repoKey}`);
    if (!res.ok) throw new Error("Failed to fetch repository details.");
    return res.json();
  },

  // Phase 2: Parsing
  parseRepo: async (repoKey: string, force = false): Promise<JobResponse> => {
    const res = await fetch(`${API_BASE}/parse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_key: repoKey, force }),
    });
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return res.json();
  },

  getParseDetail: async (repoKey: string): Promise<ParseResponse> => {
    const res = await fetch(`${API_BASE}/parse/${repoKey}`);
    if (!res.ok) throw new Error("Failed to fetch parse summary.");
    return res.json();
  },

  // Phase 3: Chunking & Embeddings
  chunkRepo: async (repoKey: string, force = false): Promise<JobResponse> => {
    const res = await fetch(`${API_BASE}/chunk`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_key: repoKey, force }),
    });
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return res.json();
  },

  // Phase 4: RAG Q&A
  askQuestion: async (repoKey: string, question: string, sessionId?: string): Promise<QAResponse> => {
    const res = await fetch(`${API_BASE}/qa`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_key: repoKey, question, session_id: sessionId }),
    });
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return res.json();
  },

  // Phase 6: Diagram
  generateDiagram: async (repoKey: string, force = false): Promise<JobResponse> => {
    const res = await fetch(`${API_BASE}/diagram`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_key: repoKey, force }),
    });
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return res.json();
  },

  getDiagramDetail: async (repoKey: string): Promise<DiagramResponse> => {
    const res = await fetch(`${API_BASE}/diagram/${repoKey}`);
    if (!res.ok) throw new Error("Failed to fetch diagram.");
    return res.json();
  },

  // Phase 7: Repponator Architectural Story
  generateStory: async (repoKey: string, force = false): Promise<JobResponse> => {
    const res = await fetch(`${API_BASE}/story`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_key: repoKey, force }),
    });
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return res.json();
  },

  getStoryDetail: async (repoKey: string): Promise<StoryResponse> => {
    const res = await fetch(`${API_BASE}/story/${repoKey}`);
    if (!res.ok) throw new Error("Failed to fetch architectural story.");
    return res.json();
  },

  // Jobs Manager Status Polling
  pollJob: async (jobId: string): Promise<JobStatusResponse> => {
    const res = await fetch(`${API_BASE}/jobs/${jobId}`);
    if (!res.ok) throw new Error("Job polling request failed.");
    return res.json();
  },
};

// Extractor helper for API error descriptions
async function getErrorMessage(response: Response): Promise<string> {
  try {
    const err = await response.json();
    return err.message || err.detail || response.statusText;
  } catch {
    return `HTTP ${response.status}: ${response.statusText}`;
  }
}
