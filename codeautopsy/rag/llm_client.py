"""
rag/llm_client.py — Unified LLM Client for Ollama and Gemini

Provides a single interface for both local (Ollama) and cloud (Gemini) LLMs.
No other module should import ollama or google.generativeai directly.
"""

import os
import time
import logging
from typing import Optional

# Import config
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    GEMINI_MODEL,
    GEMINI_RPM_LIMIT,
    MAX_ANSWER_TOKENS,
)

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when LLM operations fail."""
    pass


class LLMClient:
    """
    Unified LLM client supporting both Ollama (local) and Gemini (cloud).
    
    Usage:
        client = LLMClient()
        answer = client.generate(system_prompt, user_message)
    """
    
    def __init__(self):
        """Initialize LLM client based on LLM_PROVIDER env var or config."""
        self.provider = os.getenv("LLM_PROVIDER", LLM_PROVIDER).lower()
        self.last_request_time = 0.0
        
        if self.provider == "ollama":
            self._init_ollama()
        elif self.provider == "gemini":
            self._init_gemini()
        elif self.provider == "groq":
            self._init_groq()
        else:
            raise LLMError(
                f"Unknown LLM_PROVIDER: {self.provider}. "
                f"Must be 'ollama', 'gemini', or 'groq'"
            )
        
        logger.info(f"LLM client initialized: provider={self.provider}, model={self.model}")
    
    def _init_ollama(self):
        """Initialize Ollama client."""
        try:
            import ollama
        except ImportError:
            raise LLMError(
                "Ollama package not installed. Install with: pip install ollama\n"
                "Or use Gemini instead: set LLM_PROVIDER=gemini in .env"
            )
        
        self.client = ollama.Client(host=OLLAMA_BASE_URL)
        self.model = os.getenv("OLLAMA_MODEL", OLLAMA_MODEL)
        
        # Verify Ollama is running
        self._verify_ollama()
    
    def _init_groq(self):
        """Initialize Groq direct API client (requires zero dependencies/packages!)."""
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise LLMError(
                "GROQ_API_KEY not set in .env file.\n"
                "Please add to .env: GROQ_API_KEY=your_key_here"
            )
        self.api_key = api_key
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.model_name = self.model

    def _init_gemini(self):
        """Initialize Gemini client."""
        try:
            import google.generativeai as genai
        except ImportError:
            raise LLMError(
                "Google Generative AI package not installed. "
                "Install with: pip install google-generativeai\n"
                "Or use Ollama instead: set LLM_PROVIDER=ollama in .env"
            )
        
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise LLMError(
                "GEMINI_API_KEY not set in .env file.\n"
                "Get your free API key from: https://aistudio.google.com/app/apikey\n"
                "Then add to .env: GEMINI_API_KEY=your_key_here\n\n"
                "Or use Ollama instead:\n"
                "  1. Install from: https://ollama.ai\n"
                "  2. Run: ollama pull mistral\n"
                "  3. Run: ollama serve\n"
                "  4. Set in .env: LLM_PROVIDER=ollama"
            )
        
        genai.configure(api_key=api_key)
        self.model_name = GEMINI_MODEL
        self.genai = genai
        
        # Create model instance
        try:
            self.model = genai.GenerativeModel(self.model_name)
            logger.info(f"Gemini model initialized: {self.model_name}")
        except Exception as e:
            raise LLMError(f"Failed to initialize Gemini model: {e}")
    
    def _verify_ollama(self):
        """Verify Ollama server is running and model is available."""
        try:
            # Try to list models to verify connection
            self.client.list()
            logger.info(f"Ollama server connected at {OLLAMA_BASE_URL}")
        except Exception as e:
            raise LLMError(
                f"Ollama not running or not accessible at {OLLAMA_BASE_URL}\n"
                f"Error: {e}\n\n"
                f"To fix:\n"
                f"  1. Install Ollama from: https://ollama.ai\n"
                f"  2. Start server: ollama serve\n"
                f"  3. Pull model: ollama pull {self.model}\n\n"
                f"Or use Gemini instead:\n"
                f"  Set in .env: LLM_PROVIDER=gemini\n"
                f"  Set in .env: GEMINI_API_KEY=your_key"
            )
        
        # Verify model is pulled
        try:
            models = self.client.list()
            model_names = [m['name'] for m in models.get('models', [])]
            if not any(self.model in name for name in model_names):
                logger.warning(
                    f"Model '{self.model}' not found. Available models: {model_names}\n"
                    f"Pull it with: ollama pull {self.model}"
                )
        except Exception as e:
            logger.warning(f"Could not verify model availability: {e}")
    
    def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = MAX_ANSWER_TOKENS,
        temperature: float = 0.1
    ) -> str:
        """
        Generate a response from the LLM.
        
        Args:
            system_prompt: System instructions for the LLM
            user_message: User's question or prompt
            max_tokens: Maximum tokens in response
            temperature: Randomness (0.0-1.0, lower = more deterministic)
        
        Returns:
            Generated text response
        
        Raises:
            LLMError: If generation fails after retries
        """
        if self.provider == "ollama":
            return self._generate_ollama(system_prompt, user_message, max_tokens, temperature)
        elif self.provider == "gemini":
            return self._generate_gemini(system_prompt, user_message, max_tokens, temperature)
        elif self.provider == "groq":
            return self._generate_groq(system_prompt, user_message, max_tokens, temperature)
        else:
            raise LLMError(f"Unknown provider: {self.provider}")
    
    def _generate_groq(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        temperature: float
    ) -> str:
        """Generate response using Groq direct HTTP REST endpoint."""
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # Try using requests package first (standard), fall back to urllib if requests is missing
        try:
            import requests
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            if response.status_code != 200:
                raise LLMError(f"Groq API returned status {response.status_code}: {response.text}")
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except ImportError:
            # Fallback to python standard library urllib.request
            import urllib.request
            import json
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    res_body = response.read().decode("utf-8")
                    data = json.loads(res_body)
                    return data["choices"][0]["message"]["content"].strip()
            except Exception as ue:
                raise LLMError(f"Groq generation failed via urllib fallback: {ue}")
        except Exception as e:
            raise LLMError(f"Groq generation failed: {e}")

    def _generate_ollama(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        temperature: float
    ) -> str:
        """Generate response using Ollama."""
        max_retries = 3
        retry_delay = 2.0
        
        for attempt in range(max_retries):
            try:
                response = self.client.chat(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    options={
                        "temperature": temperature,
                        "num_predict": max_tokens
                    }
                )
                
                content = response['message']['content']
                if not content or not content.strip():
                    raise LLMError("Ollama returned empty response")
                
                return content.strip()
            
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Ollama request failed (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    time.sleep(retry_delay)
                else:
                    raise LLMError(f"Ollama generation failed after {max_retries} attempts: {e}")
        
        raise LLMError("Ollama generation failed")
    
    def _generate_gemini(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        temperature: float
    ) -> str:
        """Generate response using Gemini with rate limiting."""
        # Rate limiting: ensure we don't exceed GEMINI_RPM_LIMIT
        min_interval = 60.0 / GEMINI_RPM_LIMIT
        time_since_last = time.time() - self.last_request_time
        
        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        max_retries = 3
        retry_delay = 2.0
        
        for attempt in range(max_retries):
            try:
                # Combine system prompt and user message
                full_prompt = f"{system_prompt}\n\nUser: {user_message}"
                
                # Generate response
                response = self.model.generate_content(
                    full_prompt,
                    generation_config=self.genai.types.GenerationConfig(
                        max_output_tokens=max_tokens,
                        temperature=temperature
                    )
                )
                
                self.last_request_time = time.time()
                
                # Extract text from response
                if not response.text or not response.text.strip():
                    raise LLMError("Gemini returned empty response")
                
                return response.text.strip()
            
            except Exception as e:
                error_str = str(e).lower()
                
                # Handle rate limit errors
                if "429" in error_str or "rate limit" in error_str:
                    wait_time = 60.0 / GEMINI_RPM_LIMIT
                    logger.warning(f"Gemini rate limit hit. Waiting {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    continue
                
                # Handle quota exceeded
                if "quota" in error_str or "resource exhausted" in error_str:
                    raise LLMError(
                        "Gemini API quota exceeded. "
                        "Wait a few minutes or use Ollama instead: set LLM_PROVIDER=ollama in .env"
                    )
                
                # Retry on other errors
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Gemini request failed (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    time.sleep(retry_delay)
                else:
                    raise LLMError(f"Gemini generation failed after {max_retries} attempts: {e}")
        
        raise LLMError("Gemini generation failed")
    
    def generate_short(
        self,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 0.1
    ) -> str:
        """
        Generate a short response (for query expansion, HyDE, etc.).
        
        Args:
            prompt: Single prompt (no system/user split)
            max_tokens: Maximum tokens (default 100)
            temperature: Randomness level
        
        Returns:
            Generated text
        """
        # Use empty system prompt for short generations
        return self.generate("", prompt, max_tokens, temperature)
    
    def get_model_info(self) -> dict:
        """
        Get information about the current model.
        
        Returns:
            Dict with provider, model_name, is_local
        """
        model_name = "unknown"
        if hasattr(self, "model_name"):
            model_name = self.model_name
        elif hasattr(self, "model") and isinstance(self.model, str):
            model_name = self.model
            
        return {
            "provider": self.provider,
            "model_name": model_name,
            "is_local": self.provider == "ollama"
        }


# Test function
def test_llm_client():
    """Test the LLM client with a simple prompt."""
    print("Testing LLM Client...")
    print("=" * 60)
    
    # Load .env file
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / ".env")
    except:
        pass
    
    try:
        client = LLMClient()
        info = client.get_model_info()
        print(f"✓ LLM initialized: {info['provider']} / {info['model_name']}")
        print()
        
        # Test short generation
        print("Testing short generation...")
        response = client.generate_short(
            "Say 'Hello from CodeAutopsy!' and nothing else.",
            max_tokens=20
        )
        print(f"Response: {response}")
        print()
        
        # Test full generation
        print("Testing full generation with system prompt...")
        system = "You are a helpful coding assistant. Be concise."
        user = "What is a function in Python? Answer in one sentence."
        response = client.generate(system, user, max_tokens=100)
        print(f"Response: {response}")
        print()
        
        print("✓ All tests passed!")
        return True
    
    except LLMError as e:
        print(f"✗ LLM Error: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_llm_client()
