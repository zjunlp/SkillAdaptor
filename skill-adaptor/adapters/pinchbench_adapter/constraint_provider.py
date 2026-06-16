"""PinchBench Constraint Provider"""

from __future__ import annotations
from typing import Dict, List, Optional

class PinchBenchConstraintProvider:
    CRITICAL_CONSTRAINTS = '\n**PinchBench-Specific Constraints (Do NOT Violate):**\n\n1. **Tool Usage**\n   - Focus on tool usage patterns rather than restarting tasks\n   - Add explicit preconditions for tool parameters\n   - Validate tool outputs before proceeding to next step\n   - Do not suggest creating new tools unless explicitly required\n\n2. **File Operations**\n   - Always verify file existence before read operations\n   - Check file permissions before write operations\n   - Handle encoding issues explicitly (utf-8 default)\n\n3. **API Interactions**\n   - Validate response status codes before parsing\n   - Implement backoff on rate limit (429) errors\n   - Handle timeout errors with explicit retry limits\n\n4. **Error Recovery**\n   - Catch specific exceptions, not bare except clauses\n   - Provide fallback behavior for common failures\n   - Log errors with sufficient context for debugging\n\n5. **Code Execution**\n   - NEVER execute shell commands without validation\n   - Check return codes from subprocess calls\n   - Sanitize inputs used in command construction\n'
    FAILURE_PATTERNS: List[Dict[str, str]] = [{'pattern': 'uncaught_tool_error', 'description': 'Tool raises exception without error handling', 'solution': "Add validation: 'Wrap tool calls in try-except with specific error handling'"}, {'pattern': 'missing_file_check', 'description': 'Reading file without existence check', 'solution': "Add precondition: 'Verify file.exists() before read operations'"}, {'pattern': 'unvalidated_api_response', 'description': 'Parsing API response without status check', 'solution': "Add validation: 'Check response.status_code == 200 before parsing'"}, {'pattern': 'shell_injection', 'description': 'Constructing shell commands with user input', 'solution': "Add constraint: 'Use parameterized commands or shlex.quote() for inputs'"}]
    TOOL_GUIDANCE = {'execute': 'Always check return code and capture stderr', 'read_file': 'Verify file exists and handle encoding errors', 'write_file': 'Ensure directory exists before writing', 'api_call': 'Validate response status and handle rate limits', 'parse': 'Handle malformed data gracefully with fallbacks'}

    @classmethod
    def get_constraints(cls) -> str:
        return cls.CRITICAL_CONSTRAINTS

    @classmethod
    def get_summary(cls) -> str:
        return 'PinchBench constraints: validate-tools, handle-errors, check-before-read'

    @classmethod
    def get_failure_patterns(cls) -> List[Dict[str, str]]:
        return cls.FAILURE_PATTERNS

    @classmethod
    def get_tool_guidance(cls, tool_name: str) -> Optional[str]:
        return cls.TOOL_GUIDANCE.get(tool_name.lower())

    @classmethod
    def validate_skill_text(cls, text: str) -> tuple[bool, List[str]]:
        warnings = []
        text_lower = text.lower()
        if 'execute(' in text_lower or 'subprocess' in text_lower:
            if 'returncode' not in text_lower and 'check' not in text_lower:
                warnings.append('Warning: Shell execution without return code check')
        if 'open(' in text_lower and 'try' not in text_lower:
            warnings.append('Warning: File operation without exception handling')
        if 'request' in text_lower or 'api' in text_lower:
            if 'status_code' not in text_lower and 'status' not in text_lower:
                warnings.append('Warning: API call without status validation')
        return (len(warnings) == 0, warnings)
