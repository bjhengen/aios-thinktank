"""
Vision model wrapper for Qwen3-VL-8B (or Qwen2-VL-7B).

This module handles loading and inference with the vision-language model
that controls the robot car.
"""

import time
from typing import Optional, Tuple
import torch
from PIL import Image
import io
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info

from shared.utils import setup_logging
from server.config import config


logger = setup_logging(__name__)


class VisionModel:
    """
    Wrapper for Qwen vision-language model.

    This class handles model loading, inference, and maintains conversation
    history for context-aware control.
    """

    def __init__(self, model_name: Optional[str] = None, device: Optional[str] = None):
        """
        Initialize the vision model.

        Args:
            model_name: HuggingFace model identifier (default: from config)
            device: Device to run model on (default: from config)
        """
        self.model_name = model_name or config.model_name
        self.device = device or config.model_device
        self.model = None
        self.processor = None
        self.conversation_history = []

        logger.info(f"Initializing VisionModel: {self.model_name} on {self.device}")

    def load(self) -> None:
        """
        Load the model and processor.

        This can take significant time and memory on first load.
        """
        logger.info("Loading vision model...")
        start_time = time.time()

        try:
            # Load model with optimizations
            self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                self.model_name,
                torch_dtype=torch.bfloat16,  # Use bfloat16 for RTX 5090
                device_map="auto",
                attn_implementation="sdpa"  # Use PyTorch's scaled dot-product attention
            )

            # Load processor
            self.processor = AutoProcessor.from_pretrained(self.model_name)

            load_time = time.time() - start_time
            logger.info(f"Model loaded successfully in {load_time:.2f}s")

            # Log model info
            if hasattr(self.model, 'num_parameters'):
                params = self.model.num_parameters() / 1e9
                logger.info(f"Model parameters: {params:.2f}B")

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def process_frame(self, jpeg_data: bytes, prompt: str) -> str:
        """
        Process a camera frame with a text prompt.

        Args:
            jpeg_data: JPEG-encoded image data
            prompt: Text prompt/instruction for the model

        Returns:
            Model's text response
        """
        if self.model is None or self.processor is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        try:
            # Decode JPEG to PIL Image
            image = Image.open(io.BytesIO(jpeg_data))

            # Prepare messages for the model
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]

            # Process inputs
            text = self.processor.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )

            image_inputs, video_inputs = process_vision_info(messages)

            inputs = self.processor(
                text=[text],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt"
            )
            inputs = inputs.to(self.device)

            # Generate response
            start_time = time.time()

            with torch.no_grad():
                generated_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=config.max_new_tokens,
                    temperature=config.temperature,
                    do_sample=True
                )

            # Decode response
            generated_ids_trimmed = [
                out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            response = self.processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False
            )[0]

            inference_time = time.time() - start_time

            if config.log_inference_time:
                logger.info(f"Inference time: {inference_time:.3f}s")

            return response

        except Exception as e:
            logger.error(f"Error processing frame: {e}")
            raise

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
        if self.model is None or self.processor is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        try:
            # Decode JPEG to PIL Image
            image = Image.open(io.BytesIO(jpeg_data))

            # Build messages with history
            messages = []

            # Add relevant history (without images to save memory)
            history_to_use = self.conversation_history[-max_history:]
            for hist_prompt, hist_response in history_to_use:
                messages.append({"role": "user", "content": [{"type": "text", "text": hist_prompt}]})
                messages.append({"role": "assistant", "content": [{"type": "text", "text": hist_response}]})

            # Add current message with image
            messages.append({
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt}
                ]
            })

            # Process inputs
            text = self.processor.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )

            image_inputs, video_inputs = process_vision_info(messages)

            inputs = self.processor(
                text=[text],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt"
            )
            inputs = inputs.to(self.device)

            # Generate response
            start_time = time.time()

            with torch.no_grad():
                generated_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=config.max_new_tokens,
                    temperature=config.temperature,
                    do_sample=True
                )

            # Decode response
            generated_ids_trimmed = [
                out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            response = self.processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False
            )[0]

            inference_time = time.time() - start_time

            if config.log_inference_time:
                logger.info(f"Inference time: {inference_time:.3f}s")

            # Update history
            self.conversation_history.append((prompt, response))
            if len(self.conversation_history) > max_history * 2:
                self.conversation_history = self.conversation_history[-max_history * 2:]

            return response

        except Exception as e:
            logger.error(f"Error processing frame with history: {e}")
            raise

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history = []
        logger.info("Conversation history cleared")

    def unload(self) -> None:
        """Unload model to free memory."""
        if self.model is not None:
            del self.model
            self.model = None
        if self.processor is not None:
            del self.processor
            self.processor = None

        # Clear CUDA cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        logger.info("Model unloaded")
