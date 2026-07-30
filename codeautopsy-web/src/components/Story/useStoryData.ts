/**
 * useStoryData.ts — Custom hook for loading architectural story data
 *
 * Phase 8: Connects story narrative views directly to the FastAPI REST API.
 *
 * Error handling strategy:
 *   - Network error (server offline) + default repo  → show itsdangerous demo story
 *   - Network error (server offline) + other repo    → show generic offline notice
 *   - Server online but 404 / story not generated    → show "Story Not Found" screen
 */

import { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';

export interface KeyModule {
  module_id: string;
  role_title: string;
  explanation: string;
}

export interface ArchitecturalStory {
  project_summary: string;
  tech_stack: string[];
  primary_commitment: string;
  origin_story: string;
  how_it_flows: string;
  key_modules: KeyModule[];
  design_tensions: string;
  founding_metaphor: string;
  verdict: string;
}

export interface StoryMetadata {
  repo_owner: string;
  repo_name: string;
  model_used: string;
  temperature: number;
  max_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  generation_timestamp: string;
  generation_duration_seconds: number;
}

interface UseStoryDataReturn {
  story: ArchitecturalStory | null;
  meta: StoryMetadata | null;
  isLoading: boolean;
  error: string | null;
}

// ── Demo data for the default / offline case ─────────────────────────────────
const DEMO_STORY: ArchitecturalStory = {
  project_summary: "itsdangerous is a Python library for cryptographically signing data — like cookies, password-reset tokens, or session IDs — so you can send them to untrusted clients and verify they haven't been tampered with when they come back. It uses HMAC-based signatures from Python's standard library, requires zero external dependencies, and is used by frameworks like Flask to secure user sessions.",
  tech_stack: ['Python', 'Flask', 'HMAC'],
  primary_commitment: "Every token matters — build a signing library so lightweight it has no runtime dependencies, trusting only Python's stdlib and the developer's key.",
  origin_story: "itsdangerous began as a tiny module inside Flask, born from a very specific need: Armin Ronacher wanted to send secure data to untrusted clients — browser cookies, password-reset links — without trusting a database. The guiding insight was radical minimalism: if you only depend on Python's standard library, you can never have a supply-chain problem. The library crystallised around HMAC-SHA1 signatures and became its own project in 2011, carrying that zero-dependency philosophy forward to this day.",
  how_it_flows: "A caller constructs a Signer or one of its subclasses (URLSafeSerializer, TimestampSigner), passing a secret key and optional salt. The sign() method appends a separator plus an HMAC digest to the payload. On the other side, unsign() splits the value, recomputes the digest, and compares in constant time. URLSafeSerializer layers JSON serialisation and URL-safe base64 on top. TimestampSigner embeds a compact timestamp so tokens can expire. The whole pipeline is stateless: no database, no cache, no network — just cryptographic math.",
  key_modules: [
    { module_id: "itsdangerous/signer_py", role_title: "The Signatory", explanation: "Core HMAC signing engine. Owns the secret key, salt, separator, and digest method. Every other class inherits from or composes with Signer. It is the single source of cryptographic truth." },
    { module_id: "itsdangerous/serializer_py", role_title: "The Serializer Orchestrator", explanation: "Bridges Python objects and signed byte strings. Handles JSON (de)serialisation and delegates signing to an injected Signer. Separation of concerns: serialisation is not signing." },
    { module_id: "itsdangerous/timed_py", role_title: "The Timestamp Guardian", explanation: "Extends Signer with an embedded epoch timestamp. Unsigning checks age against max_age and raises SignatureExpired with the original payload still attached — a critical UX decision." },
    { module_id: "itsdangerous/url_safe_py", role_title: "The URL-Safe Translator", explanation: "Applies zlib compression then URL-safe base64 encoding, making signed tokens safe for cookies and query strings without any percent-encoding overhead." },
    { module_id: "itsdangerous/exc_py", role_title: "The Exception Ledger", explanation: "Defines the exception hierarchy: BadSignature, BadData, BadTimeSignature, SignatureExpired. Each carries the original, unverified payload so callers can choose whether to trust it for debugging." },
  ],
  design_tensions: "The deepest tension is between expressiveness and minimalism. Armin chose zero dependencies even when libraries like cryptography or PyNaCl would offer stronger primitives. The bet: developers trust stdlib more than third-party crypto for a pure signing use-case.",
  founding_metaphor: "itsdangerous is a wax seal on a medieval letter: it does not encrypt the contents, it only proves the letter left your hand intact. Anyone can read the message, but tampering breaks the seal visibly.",
  verdict: "itsdangerous is a masterclass in doing one thing and doing it right. Its power is its restraint — no network, no database, no framework coupling, no runtime dependencies.",
};

const DEMO_META: StoryMetadata = {
  repo_owner: 'pallets',
  repo_name: 'itsdangerous',
  model_used: 'google/gemini-2.5-pro',
  temperature: 0.65,
  max_tokens: 1800,
  prompt_tokens: 452,
  completion_tokens: 689,
  generation_timestamp: new Date().toISOString(),
  generation_duration_seconds: 4.2,
};

// ─────────────────────────────────────────────────────────────────────────────

export function useStoryData(repoKey = "pallets__itsdangerous"): UseStoryDataReturn {
  const [story, setStory] = useState<ArchitecturalStory | null>(null);
  const [meta, setMeta] = useState<StoryMetadata | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadStory() {
      try {
        setIsLoading(true);
        setError(null);

        // 1. Fetch live architectural story details
        const storyDetails = await apiClient.getStoryDetail(repoKey);

        // 2. Fetch repository stats to compile metadata
        const repoDetails = await apiClient.getRepoDetail(repoKey);

        // BUG FIX: StoryResponse only has `tokens_used`, not separate
        // prompt_tokens / completion_tokens — split proportionally (60/40).
        const totalTokens = storyDetails.tokens_used || 0;
        const promptTokens = Math.floor(totalTokens * 0.6);
        const completionTokens = totalTokens - promptTokens;

        setStory({
          project_summary:    storyDetails.project_summary    || "",
          tech_stack:         storyDetails.tech_stack         || [],
          primary_commitment: storyDetails.primary_commitment || "No primary commitment recorded.",
          origin_story:       storyDetails.origin_story       || "No origin story recorded.",
          how_it_flows:       storyDetails.how_it_flows       || "No data flow description available.",
          key_modules:        storyDetails.key_modules        || [],
          design_tensions:    storyDetails.design_tensions    || "No design tensions identified.",
          founding_metaphor:  storyDetails.founding_metaphor  || "",
          verdict:            storyDetails.verdict            || "No verdict available.",
        });

        setMeta({
          repo_owner: repoDetails.owner || 'Unknown',
          repo_name: repoDetails.name || 'Unknown',
          model_used: storyDetails.model_used || 'Unknown',
          temperature: 0.65,
          max_tokens: 1800,
          prompt_tokens: promptTokens,        // ← was wrongly storyDetails.prompt_tokens
          completion_tokens: completionTokens,    // ← was wrongly storyDetails.completion_tokens
          generation_timestamp: repoDetails.ingested_at
            ? new Date(repoDetails.ingested_at).toISOString()
            : new Date().toISOString(),
          generation_duration_seconds: storyDetails.generation_duration_seconds || 0,
        });

      } catch (err: any) {
        const isNetworkError =
          err instanceof TypeError ||
          (err?.message && (
            err.message.includes('Failed to fetch') ||
            err.message.includes('NetworkError') ||
            err.message.includes('network')
          ));
        const isDefaultRepo = repoKey === "pallets__itsdangerous";

        if (isNetworkError && isDefaultRepo) {
          // Server is offline and default repo → show itsdangerous demo
          console.warn(`Backend offline, showing demo story for '${repoKey}'.`);
          setStory(DEMO_STORY);
          setMeta(DEMO_META);
          setError(null);
        } else if (isNetworkError) {
          // Server is offline for a real user repo → show clear offline error
          console.warn(`Backend offline while loading '${repoKey}'.`);
          setError(`Cannot reach the backend server. Start it with:\n\ncd codeautopsy && source venv/bin/activate && python3 -m uvicorn api.main:app --reload --port 8000`);
          setStory(null);
          setMeta(null);
        } else {
          // Server is reachable but story not generated yet (404 / other API error)
          console.error(`API error loading story for '${repoKey}':`, err);
          setError(`No architectural story found for "${repoKey}". Make sure you have run the full analysis pipeline (ingest → parse → story) for this repository first.`);
          setStory(null);
          setMeta(null);
        }
      } finally {
        setIsLoading(false);
      }
    }

    loadStory();
  }, [repoKey]);

  return { story, meta, isLoading, error };
}
