"""
story/repponator.py — Repponator Story Generator

Generates editorial-quality architectural narratives using Groq LLM.
"""

import json
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# Repponator System Prompt (DO NOT CHANGE)
REPPONATOR_SYSTEM_PROMPT = """You are Repponator — an architectural narrator who reads codebases the way historians read civilisations.

Your job is NOT to summarise what code does. Your job is to explain WHY it was built that way.

Every well-designed codebase has one founding architectural commitment — a single, irreversible decision made early on that forced all subsequent decisions. Find it. Name it clearly. Trace everything back to it.

Write like an architect explaining a building to a curious senior engineer. Use short paragraphs. Be precise and insightful. Never be vague. Do not use bullet points anywhere. This is flowing prose, written to be read from top to bottom."""


class Repponator:
    """
    The Repponator — generates architectural stories from structural analysis.
    """
    
    TEMPERATURE = 0.65  # Creative but grounded
    MAX_TOKENS = 1800
    
    def __init__(self, repo_folder: Path):
        """
        Initialize Repponator.
        
        Args:
            repo_folder: Path to repo folder
        """
        self.repo_folder = repo_folder
        self.output_folder = repo_folder / "story"
        
        # Load environment variables
        from dotenv import load_dotenv
        import os
        env_path = Path(__file__).parent.parent / ".env"
        load_dotenv(env_path)
        
        # Initialize LLM client
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from rag.llm_client import LLMClient
        
        self.llm_client = LLMClient()
    
    def generate_story(self, context, force: bool = False):
        """
        Generate architectural story.
        
        Args:
            context: StoryContext dataclass
            force: If True, regenerate even if story exists
        
        Returns:
            (ArchitecturalStory, StoryMetadata)
        """
        from story import ArchitecturalStory, StoryMetadata, KeyModule
        
        # Check if already generated
        story_path = self.output_folder / "story_output.json"
        if story_path.exists() and not force:
            logger.info("Story already generated. Use --force to regenerate.")
            return self._load_existing_story()
        
        logger.info("Generating architectural story with Repponator...")
        
        # Build user prompt
        user_prompt = self._build_user_prompt(context)
        
        # Call LLM
        start_time = time.time()
        
        try:
            response_text = self.llm_client.generate(
                system_prompt=REPPONATOR_SYSTEM_PROMPT,
                user_message=user_prompt,
                max_tokens=self.MAX_TOKENS,
                temperature=self.TEMPERATURE
            )
            
            generation_duration = time.time() - start_time
            
            # Parse JSON response
            story_dict = self._parse_response(response_text)
            
            # Build ArchitecturalStory
            key_modules = [
                KeyModule(
                    module_id=m["module_id"],
                    role_title=m["role_title"],
                    explanation=m["explanation"]
                )
                for m in story_dict.get("key_modules", [])
            ]
            
            story = ArchitecturalStory(
                primary_commitment=story_dict.get("primary_commitment", ""),
                origin_story=story_dict.get("origin_story", ""),
                how_it_flows=story_dict.get("how_it_flows", ""),
                key_modules=key_modules,
                design_tensions=story_dict.get("design_tensions", ""),
                founding_metaphor=story_dict.get("founding_metaphor", ""),
                verdict=story_dict.get("verdict", "")
            )
            
            # Build metadata
            model_info = self.llm_client.get_model_info()
            
            metadata = StoryMetadata(
                repo_owner=context.repo_name.split("/")[0] if "/" in context.repo_name else "",
                repo_name=context.repo_name.split("/")[1] if "/" in context.repo_name else context.repo_name,
                model_used=f"{model_info['provider']}/{model_info['model_name']}",
                temperature=self.TEMPERATURE,
                max_tokens=self.MAX_TOKENS,
                prompt_tokens=len(user_prompt.split()),  # Rough estimate
                completion_tokens=len(response_text.split()),  # Rough estimate
                generation_timestamp=datetime.now().isoformat(),
                generation_duration_seconds=generation_duration
            )
            
            # Save outputs
            self._save_story(story, metadata)
            
            logger.info(f"✓ Story generated in {generation_duration:.1f}s")
            
            return story, metadata
        
        except Exception as e:
            logger.error(f"Failed to generate story: {e}")
            
            # Generate fallback story for small repos
            if context.total_files < 5:
                return self._generate_fallback_story(context)
            
            raise
    
    def _build_user_prompt(self, context) -> str:
        """Build user prompt from context."""
        # Build top modules summary
        top_modules_summary = []
        for module in context.top_modules[:5]:  # Top 5 only
            funcs = ", ".join(module.function_names[:4])  # Max 4 functions
            classes = ", ".join(module.class_names[:3])  # Max 3 classes
            
            summary = f"{module.filename}"
            if classes:
                summary += f" (classes: {classes})"
            if funcs:
                summary += f" (functions: {funcs})"
            summary += f" [called by {module.called_by_count}, calls {module.calls_count}]"
            
            top_modules_summary.append(summary)
        
        prompt = f"""Analyse this codebase and write its architectural story.

Repository: {context.repo_name}
Repository Description: {context.repo_description or 'No description provided.'}
Language Breakdown: {context.languages_breakdown or context.primary_language}
Detected Architectural Pattern: {context.detected_pattern}
Entry Points: {', '.join(context.entry_points) if context.entry_points else 'None detected'}
Core Utility Files: {', '.join(context.core_utilities) if context.core_utilities else 'None'}
Top Modules by Call Volume:
{chr(10).join('  - ' + s for s in top_modules_summary)}
Architectural Signals Detected: {', '.join(context.architectural_signals) if context.architectural_signals else 'None'}
Circular Dependencies Present: {'Yes' if context.has_circular_deps else 'No'}
Complexity Hotspots: {', '.join(context.complexity_hotspots) if context.complexity_hotspots else 'None'}

CRITICAL GUIDELINE: The codebase may contain multiple languages or sub-projects (e.g. a frontend client/landing page and a backend service/model). Identify and focus the architectural narrative around the CORE domain logic (the actual machine learning model, core business service, or primary functional backend engine — for example, fake-or-real audio classification models/apis) rather than just detailing basic UI components, configuration boilerplate, or boilerplate wrappers. Keep the primary commitment, origin story, and modules grounded in this core engine.

Return your response as valid JSON with exactly this structure:
{{
  "primary_commitment": "One sentence naming the founding architectural decision.",
  "origin_story": "2-3 sentences explaining why this commitment was likely made and what problem it solved.",
  "how_it_flows": "3-4 sentences describing how data and control flow through the system as a direct consequence of the primary commitment.",
  "key_modules": [
    {{
      "module_id": "filename used as diagram node id",
      "role_title": "Short poetic role name — e.g. The Gateway, The Orchestrator, The Ledger",
      "explanation": "2 sentences explaining what this module does and why it exists exactly where it does in the architecture."
    }}
  ], // Return exactly 3 to 5 key modules (no fewer than 3) corresponding to the most critical modules.
  "design_tensions": "2-3 sentences naming the trade-offs and sacrifices the architecture had to make.",
  "founding_metaphor": "One vivid metaphor that captures the entire architecture in a single sentence.",
  "verdict": "2 sentences honestly assessing whether this is a well-constructed architecture and what would break it."
}}"""
        
        return prompt
    
    def _parse_response(self, response_text: str) -> dict:
        """
        Parse JSON response from LLM.
        
        Retries once with stricter prompt if parsing fails.
        """
        # Try to extract JSON from response
        # Sometimes LLM wraps JSON in markdown code blocks
        text = response_text.strip()
        
        # Remove markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        
        if text.endswith("```"):
            text = text[:-3]
        
        text = text.strip()
        
        try:
            story_dict = json.loads(text)
            
            # Validate required fields
            required_fields = [
                "primary_commitment",
                "origin_story",
                "how_it_flows",
                "key_modules",
                "design_tensions",
                "founding_metaphor",
                "verdict"
            ]
            
            for field in required_fields:
                if field not in story_dict:
                    raise ValueError(f"Missing required field: {field}")
            
            return story_dict
        
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.error(f"Response text: {response_text[:500]}...")
            
            # TODO: Retry with stricter prompt
            raise ValueError(f"LLM returned invalid JSON: {e}")
    
    def _generate_fallback_story(self, context):
        """Generate fallback story for small repos."""
        from story import ArchitecturalStory, StoryMetadata, KeyModule
        
        logger.warning("Generating fallback story for small repo")
        
        story = ArchitecturalStory(
            primary_commitment=f"This is a minimal {context.primary_language} library with {context.total_files} files.",
            origin_story=f"The codebase is intentionally small and focused. With only {context.total_functions} functions across {context.total_files} files, it prioritizes simplicity over architectural complexity.",
            how_it_flows="The control flow is straightforward and linear. There are no complex abstractions or layered architectures — just direct function calls serving a single, well-defined purpose.",
            key_modules=[
                KeyModule(
                    module_id=m.filename.replace(".", "_"),
                    role_title="Core Module",
                    explanation=f"Contains {len(m.function_names)} functions. This module handles the primary logic of the library."
                )
                for m in context.top_modules[:3]
            ],
            design_tensions="The main tension is between keeping the codebase minimal and adding features. Every new function risks bloating what should remain a focused tool.",
            founding_metaphor="This codebase is a Swiss Army knife — small, portable, and designed to do one thing exceptionally well.",
            verdict="This is a well-constructed minimal library. It would break if feature creep led to architectural complexity without a corresponding refactor into proper layers."
        )
        
        metadata = StoryMetadata(
            repo_owner=context.repo_name.split("/")[0] if "/" in context.repo_name else "",
            repo_name=context.repo_name.split("/")[1] if "/" in context.repo_name else context.repo_name,
            model_used="fallback/manual",
            temperature=0.0,
            max_tokens=0,
            prompt_tokens=0,
            completion_tokens=0,
            generation_timestamp=datetime.now().isoformat(),
            generation_duration_seconds=0.0
        )
        
        self._save_story(story, metadata)
        
        return story, metadata
    
    def _save_story(self, story, metadata):
        """Save story and metadata to files."""
        self.output_folder.mkdir(exist_ok=True)
        
        # Save story
        story_path = self.output_folder / "story_output.json"
        story_dict = {
            "primary_commitment": story.primary_commitment,
            "origin_story": story.origin_story,
            "how_it_flows": story.how_it_flows,
            "key_modules": [
                {
                    "module_id": m.module_id,
                    "role_title": m.role_title,
                    "explanation": m.explanation
                }
                for m in story.key_modules
            ],
            "design_tensions": story.design_tensions,
            "founding_metaphor": story.founding_metaphor,
            "verdict": story.verdict
        }
        
        with open(story_path, "w") as f:
            json.dump(story_dict, f, indent=2)
        
        logger.info(f"Saved story to {story_path}")
        
        # Save metadata
        meta_path = self.output_folder / "story_meta.json"
        meta_dict = {
            "repo_owner": metadata.repo_owner,
            "repo_name": metadata.repo_name,
            "model_used": metadata.model_used,
            "temperature": metadata.temperature,
            "max_tokens": metadata.max_tokens,
            "prompt_tokens": metadata.prompt_tokens,
            "completion_tokens": metadata.completion_tokens,
            "generation_timestamp": metadata.generation_timestamp,
            "generation_duration_seconds": metadata.generation_duration_seconds
        }
        
        with open(meta_path, "w") as f:
            json.dump(meta_dict, f, indent=2)
        
        logger.info(f"Saved metadata to {meta_path}")
    
    def _load_existing_story(self):
        """Load existing story from files."""
        from story import ArchitecturalStory, StoryMetadata, KeyModule
        
        story_path = self.output_folder / "story_output.json"
        meta_path = self.output_folder / "story_meta.json"
        
        with open(story_path, "r") as f:
            story_dict = json.load(f)
        
        with open(meta_path, "r") as f:
            meta_dict = json.load(f)
        
        # Build ArchitecturalStory
        key_modules = [
            KeyModule(
                module_id=m["module_id"],
                role_title=m["role_title"],
                explanation=m["explanation"]
            )
            for m in story_dict.get("key_modules", [])
        ]
        
        story = ArchitecturalStory(
            primary_commitment=story_dict.get("primary_commitment", ""),
            origin_story=story_dict.get("origin_story", ""),
            how_it_flows=story_dict.get("how_it_flows", ""),
            key_modules=key_modules,
            design_tensions=story_dict.get("design_tensions", ""),
            founding_metaphor=story_dict.get("founding_metaphor", ""),
            verdict=story_dict.get("verdict", "")
        )
        
        metadata = StoryMetadata(
            repo_owner=meta_dict.get("repo_owner", ""),
            repo_name=meta_dict.get("repo_name", ""),
            model_used=meta_dict.get("model_used", ""),
            temperature=meta_dict.get("temperature", 0.0),
            max_tokens=meta_dict.get("max_tokens", 0),
            prompt_tokens=meta_dict.get("prompt_tokens", 0),
            completion_tokens=meta_dict.get("completion_tokens", 0),
            generation_timestamp=meta_dict.get("generation_timestamp", ""),
            generation_duration_seconds=meta_dict.get("generation_duration_seconds", 0.0)
        )
        
        return story, metadata


def generate_architectural_story(repo_folder: Path, force: bool = False):
    """
    Generate architectural story for a repository.
    
    Args:
        repo_folder: Path to repo folder
        force: If True, regenerate even if story exists
    
    Returns:
        (ArchitecturalStory, StoryMetadata)
    """
    from story.context_builder import StoryContextBuilder
    
    # Build context
    context_builder = StoryContextBuilder(repo_folder)
    context = context_builder.build()
    
    # Generate story
    repponator = Repponator(repo_folder)
    story, metadata = repponator.generate_story(context, force=force)
    
    return story, metadata


# Test function
if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    print("Testing Repponator...")
    print("=" * 60)
    
    # Test with itsdangerous repo
    repo_folder = Path(__file__).parent.parent / "data" / "repos" / "pallets__itsdangerous"
    
    if not repo_folder.exists():
        print("✗ Test repo not found. Run Phase 2 first on pallets/itsdangerous")
        sys.exit(1)
    
    try:
        story, metadata = generate_architectural_story(repo_folder, force=True)
        
        print(f"✓ Generated story:")
        print(f"  Primary Commitment: {story.primary_commitment[:80]}...")
        print(f"  Key Modules: {len(story.key_modules)}")
        print(f"  Model: {metadata.model_used}")
        print(f"  Duration: {metadata.generation_duration_seconds:.1f}s")
        print()
        print("✓ Repponator tests complete!")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
