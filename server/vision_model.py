"""
Vision model wrapper using llama-swap (OpenAI-compatible API).

This module handles inference with the vision-language model
that controls the robot car, via HTTP to llama-swap on port 8200.
"""

import base64
import time
from typing import Optional

import requests

from shared.utils import setup_logging
from server.config import config


logger = setup_logging(__name__)


class VisionModel:
    """
    Wrapper for vision-language model via llama-swap HTTP API.

    Uses OpenAI-compatible /v1/chat/completions endpoint with base64 images.
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or config.model_name
        self.api_url = f"{config.llama_swap_url}/v1/chat/completions"
        self.session = None
        self.conversation_history = []

        logger.info(f"Initializing VisionModel: {self.model_name} via {config.llama_swap_url}")

    def load(self) -> None:
        """Create HTTP session and verify llama-swap connectivity."""
        logger.info("Connecting to llama-swap...")
        start_time = time.time()

        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        # Test connectivity
        try:
            resp = self.session.get(
                f"{config.llama_swap_url}/v1/models",
                timeout=5.0
            )
            resp.raise_for_status()
            logger.info(f"llama-swap connected, available models: {resp.json()}")
        except requests.RequestException as e:
            logger.warning(f"Could not list models (non-fatal): {e}")

        # Pre-warm: send a tiny request to trigger model loading
        logger.info("Pre-warming model (this may take a moment on first load)...")
        try:
            warmup_messages = [
                {"role": "user", "content": "Hi"}
            ]
            self._call_api(warmup_messages, max_tokens=5)
            load_time = time.time() - start_time
            logger.info(f"Model ready in {load_time:.2f}s")
        except Exception as e:
            logger.warning(f"Pre-warm failed (will retry on first frame): {e}")

    def process_frame(self, jpeg_data: bytes, prompt: str) -> str:
        """
        Process a camera frame with a text prompt.

        Args:
            jpeg_data: JPEG-encoded image data
            prompt: Text prompt/instruction for the model

        Returns:
            Model's text response
        """
        b64_image = base64.b64encode(jpeg_data).decode('utf-8')

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}
                    },
                    {"type": "text", "text": prompt}
                ]
            }
        ]

        return self._call_api(messages)

    def process_with_history(self,
                             jpeg_data: bytes,
                             prompt: str,
                             max_history: int = 5) -> str:
        """
        Process a frame with conversation history for context.

        Args:
            jpeg_data: JPEG-encoded image data
            prompt: Text prompt/instruction for the model
            max_history: Maximum number of previous exchanges to include

        Returns:
            Model's text response
        """
        b64_image = base64.b64encode(jpeg_data).decode('utf-8')

        # Build messages with text-only history
        messages = []
        history_to_use = self.conversation_history[-max_history:]
        for hist_prompt, hist_response in history_to_use:
            messages.append({"role": "user", "content": hist_prompt})
            messages.append({"role": "assistant", "content": hist_response})

        # Current message with image
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}
                },
                {"type": "text", "text": prompt}
            ]
        })

        response = self._call_api(messages)

        # Update history
        self.conversation_history.append((prompt, response))
        if len(self.conversation_history) > max_history * 2:
            self.conversation_history = self.conversation_history[-max_history * 2:]

        return response

    def _call_api(self, messages: list, max_tokens: Optional[int] = None) -> str:
        """
        Make an API call to llama-swap.

        Returns the response content string, or a safe stop message on failure.
        """
        if self.session is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens or config.max_new_tokens,
            "temperature": config.temperature,
            "chat_template_kwargs": {"enable_thinking": False},
        }

        start_time = time.time()

        try:
            resp = self.session.post(
                self.api_url,
                json=payload,
                timeout=config.inference_timeout
            )
            resp.raise_for_status()

            result = resp.json()
            content = result["choices"][0]["message"]["content"]

            inference_time = time.time() - start_time
            if config.log_inference_time:
                usage = result.get("usage", {})
                tokens = usage.get("completion_tokens", "?")
                logger.info(f"Inference: {inference_time:.3f}s, tokens: {tokens}")

            return content

        except requests.Timeout:
            logger.error(f"llama-swap timeout after {config.inference_timeout}s")
            return "OBSERVATION: Request timed out\nASSESSMENT: Cannot process\nCOMMAND: 0,0,2,2,0\nREASONING: Timeout - stopping for safety"

        except requests.RequestException as e:
            logger.error(f"llama-swap request failed: {e}")
            return "OBSERVATION: API error\nASSESSMENT: Cannot process\nCOMMAND: 0,0,2,2,0\nREASONING: API error - stopping for safety"

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history = []
        logger.info("Conversation history cleared")

    def unload(self) -> None:
        """Close HTTP session."""
        if self.session is not None:
            self.session.close()
            self.session = None
        logger.info("Vision model session closed")
