"""
Structured Output — JSON Mode & Schema Enforcement for Agent responses.

Provides:
- ``JsonSchemaValidator`` — validate LLM output against a JSON Schema
- ``StructuredOutputMixin`` — mixin for LLM implementations to add response_format
- ``generate_structured`` — one-shot structured generation with retry+fallback
- ``StructuredOutputError`` — typed error for schema mismatch

Usage::

    from app.core.llm.structured_output import generate_structured
    from app.core.llm import get_llm

    schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
    result = await generate_structured(get_llm(), "What is AI?", schema)
    # result = {"answer": "AI is..."}
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .base import BaseLLM, ChatMessage, LLMResponse

logger = logging.getLogger(__name__)


# ── Error model ──────────────────────────────────────────────────────────


class StructuredOutputError(ValueError):
    """Raised when the model output fails schema validation after all retries."""

    def __init__(self, message: str, raw_output: str = "", validation_errors: list[str] | None = None):
        super().__init__(message)
        self.raw_output = raw_output
        self.validation_errors = validation_errors or []


# ── JSON Schema validator ────────────────────────────────────────────────


@dataclass
class SchemaValidationResult:
    valid: bool
    data: Any | None = None
    errors: list[str] = field(default_factory=list)


class JsonSchemaValidator:
    """Lightweight JSON Schema validator for structured output enforcement.

    Supports a practical subset of JSON Schema Draft 2020-12:
      - type (string, number, integer, boolean, array, object, null)
      - properties, required, additionalProperties
      - items (arrays), enum, const
      - minimum / maximum (number/integer)
      - minLength / maxLength (string)
      - minItems / maxItems (array)
      - pattern (string regex)
      - nested objects/arrays via recursive validation
      - oneOf / anyOf / allOf

    This is deliberately NOT a full JSON Schema validator — it focuses on
    the subset that LLMs can reliably produce.  For complex validation,
    defer to a post-processing step.
    """

    def validate(self, instance: Any, schema: dict[str, Any]) -> SchemaValidationResult:
        """Validate *instance* against *schema*.  Returns a result object."""
        errors: list[str] = []
        try:
            self._validate(instance, schema, "$", errors)
        except Exception as exc:
            errors.append(f"$: validation panic — {exc}")
        if errors:
            return SchemaValidationResult(valid=False, errors=errors)
        return SchemaValidationResult(valid=True, data=instance)

    # ── internal ──────────────────────────────────────────────────────

    def _validate(self, instance: Any, schema: dict[str, Any], path: str, errors: list[str]) -> None:
        if not isinstance(schema, dict):
            return

        # ── type check ────────────────────────────────────────────────
        expected = schema.get("type")
        if expected:
            if not self._check_type(instance, expected):
                errors.append(f"{path}: expected {expected}, got {type(instance).__name__}")
                return  # stop cascading for wrong-type

        # ── string constraints ─────────────────────────────────────────
        if isinstance(instance, str):
            if "minLength" in schema and len(instance) < schema["minLength"]:
                errors.append(f"{path}: length {len(instance)} < minLength {schema['minLength']}")
            if "maxLength" in schema and len(instance) > schema["maxLength"]:
                errors.append(f"{path}: length {len(instance)} > maxLength {schema['maxLength']}")
            if "pattern" in schema:
                import re
                if not re.search(schema["pattern"], instance):
                    errors.append(f"{path}: does not match pattern {schema['pattern']}")

        # ── number/integer constraints ─────────────────────────────────
        if isinstance(instance, (int, float)) and not isinstance(instance, bool):
            if "minimum" in schema and instance < schema["minimum"]:
                errors.append(f"{path}: {instance} < minimum {schema['minimum']}")
            if "maximum" in schema and instance > schema["maximum"]:
                errors.append(f"{path}: {instance} > maximum {schema['maximum']}")

        # ── enum ──────────────────────────────────────────────────────
        if "enum" in schema and instance not in schema["enum"]:
            errors.append(f"{path}: {instance!r} not in enum {schema['enum']}")

        # ── const ─────────────────────────────────────────────────────
        if "const" in schema and instance != schema["const"]:
            errors.append(f"{path}: {instance!r} != const {schema['const']!r}")

        # ── array constraints ─────────────────────────────────────────
        if isinstance(instance, list):
            if "minItems" in schema and len(instance) < schema["minItems"]:
                errors.append(f"{path}: length {len(instance)} < minItems {schema['minItems']}")
            if "maxItems" in schema and len(instance) > schema["maxItems"]:
                errors.append(f"{path}: length {len(instance)} > maxItems {schema['maxItems']}")
            if "items" in schema and isinstance(schema["items"], dict):
                for i, item in enumerate(instance):
                    self._validate(item, schema["items"], f"{path}[{i}]", errors)

        # ── object constraints ─────────────────────────────────────────
        if isinstance(instance, dict):
            if schema.get("required"):
                for key in schema["required"]:
                    if key not in instance:
                        errors.append(f"{path}: missing required property '{key}'")

            properties = schema.get("properties", {})
            if properties:
                for key, value in instance.items():
                    if key in properties:
                        self._validate(value, properties[key], f"{path}.{key}", errors)
                    elif schema.get("additionalProperties") is False:
                        errors.append(f"{path}: additional property '{key}' not allowed")

        # ── oneOf / anyOf / allOf ──────────────────────────────────────
        for comb_key in ("oneOf", "anyOf", "allOf"):
            subschemas = schema.get(comb_key)
            if isinstance(subschemas, list):
                match_count = 0
                sub_errors: list[str] = []
                for i, subschema in enumerate(subschemas):
                    sub_result = self.validate(instance, subschema)
                    if sub_result.valid:
                        match_count += 1
                    else:
                        sub_errors.extend(sub_result.errors)
                if comb_key == "allOf" and match_count != len(subschemas):
                    errors.append(f"{path}: allOf requires all subschemas to match; {match_count}/{len(subschemas)} matched")
                elif comb_key == "oneOf" and match_count != 1:
                    errors.append(f"{path}: oneOf requires exactly 1 match; got {match_count}")
                elif comb_key == "anyOf" and match_count == 0:
                    errors.append(f"{path}: anyOf requires at least 1 match")

    @staticmethod
    def _check_type(instance: Any, expected: str) -> bool:
        if expected == "string":
            return isinstance(instance, str)
        if expected == "number":
            return isinstance(instance, (int, float)) and not isinstance(instance, bool)
        if expected == "integer":
            return isinstance(instance, int) and not isinstance(instance, bool)
        if expected == "boolean":
            return isinstance(instance, bool)
        if expected == "array":
            return isinstance(instance, list)
        if expected == "object":
            return isinstance(instance, dict)
        if expected == "null":
            return instance is None
        return False  # unknown type


# ── Main API ─────────────────────────────────────────────────────────────


_STRUCTURED_SYSTEM_PROMPT = (
    "You are an AI that MUST respond with valid JSON ONLY. "
    "Do not include markdown fences, explanations, or any text outside the JSON object. "
    "Your entire response must be a single JSON object that conforms to the schema below."
)

_STRUCTURED_RETRY_PROMPT = (
    "Your previous response did not match the required JSON schema. "
    "Please correct your response.  Respond with ONLY valid JSON — no markdown, "
    "no explanation, no extra text.\n\n"
    "Validation errors:\n{errors}\n\n"
    "Required schema:\n{schema}\n\n"
    "Respond with a single JSON object that matches this schema."
)

# ── Format templates by provider ─────────────────────────────────────────
# Each provider has a different way to request structured output.
# We apply the best available method for each.

_OPENAI_JSON_MODE_SYSTEM = (
    "You MUST respond with a single valid JSON object and nothing else. "
    "Do not wrap the response in markdown code fences. "
    "The JSON must match the schema described below.\n\n"
    "Schema:\n{schema_desc}"
)

_MAX_STRUCTURED_RETRIES = 2


async def generate_structured(
    llm: BaseLLM,
    prompt: str,
    output_schema: dict[str, Any],
    *,
    system_prompt: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    max_retries: int = _MAX_STRUCTURED_RETRIES,
    validator: JsonSchemaValidator | None = None,
) -> dict[str, Any]:
    """Generate a structured JSON response from the LLM.

    Parameters
    ----------
    llm : BaseLLM
        The LLM instance to use.
    prompt : str
        The user prompt.
    output_schema : dict
        JSON Schema that the response must conform to.
    system_prompt : str, optional
        Custom system prompt (overrides the default structured-output prompt).
    temperature : float
        Sampling temperature (default 0.2 for more deterministic output).
    max_tokens : int
        Max tokens in the response.
    max_retries : int
        Number of retries on schema validation failure (default 2).
    validator : JsonSchemaValidator, optional
        Custom validator instance.

    Returns
    -------
    dict
        The parsed and validated JSON response.

    Raises
    ------
    StructuredOutputError
        If the model fails to produce valid JSON after all retries.
    """
    v = validator or JsonSchemaValidator()

    schema_desc = json.dumps(output_schema, ensure_ascii=False, indent=2)
    sys = system_prompt or f"{_STRUCTURED_SYSTEM_PROMPT}\n\nSchema:\n{schema_desc}"

    messages: list[ChatMessage] = [
        ChatMessage(role="system", content=sys),
        ChatMessage(role="user", content=prompt),
    ]

    last_raw = ""
    for attempt in range(max_retries + 1):
        try:
            response: LLMResponse = await llm.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            raise StructuredOutputError(
                f"LLM call failed on attempt {attempt + 1}: {exc}",
                raw_output=last_raw,
            ) from exc

        raw = response.content.strip()
        last_raw = raw

        # ── Extract JSON from model output ──────────────────────────
        parsed = _extract_json(raw)
        if parsed is None:
            if attempt < max_retries:
                messages.append(ChatMessage(role="assistant", content=raw))
                messages.append(ChatMessage(
                    role="user",
                    content=_STRUCTURED_RETRY_PROMPT.format(
                        errors="Response is not valid JSON.",
                        schema=schema_desc,
                    ),
                ))
                continue
            raise StructuredOutputError(
                "Model did not produce valid JSON after all attempts",
                raw_output=raw,
            )

        # ── Validate against schema ─────────────────────────────────
        result = v.validate(parsed, output_schema)
        if result.valid:
            return parsed

        if attempt < max_retries:
            # Include validation errors in the retry prompt
            error_lines = "\n".join(f"  - {e}" for e in result.errors)
            messages.append(ChatMessage(role="assistant", content=raw))
            messages.append(ChatMessage(
                role="user",
                content=_STRUCTURED_RETRY_PROMPT.format(
                    errors=error_lines,
                    schema=schema_desc,
                ),
            ))
        else:
            raise StructuredOutputError(
                f"Schema validation failed after {max_retries + 1} attempts",
                raw_output=raw,
                validation_errors=result.errors,
            )

    # Should not reach here, but keep type-checker happy
    raise StructuredOutputError("Unexpected error", raw_output=last_raw)


def _extract_json(text: str) -> Any | None:
    """Extract a JSON object from model output that may include markdown fences or surrounding text.

    Tries (in order):
      1. Entire text as-is
      2. Content inside ```json ... ``` fences
      3. Content inside ``` ... ``` fences (any language tag)
      4. First { ... } span via JSONDecoder
    """
    import re

    text = text.strip()
    if not text:
        return None

    # 1. Direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. ```json ... ``` fence
    m = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. ``` ... ``` (any language)
    m = re.search(r"```\w*\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # 4. First { ... } span
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text[match.start():])
            return obj
        except json.JSONDecodeError:
            continue

    return None
