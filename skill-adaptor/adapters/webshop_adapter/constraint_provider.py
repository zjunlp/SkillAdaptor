"""WebShop Constraint Provider"""

from __future__ import annotations
from typing import Dict, List, Optional

class WebShopConstraintProvider:
    CRITICAL_CONSTRAINTS = '\n**WebShop-Specific Constraints (Do NOT Violate):**\n\n1. **Search Behavior**\n   - **NEVER** use words like "Refine", "refine", or "go back to search"\n   - **NEVER** imply "return to search page" or "start over with better keywords"\n   - **ALWAYS** prefer "Include X in the initial search query" over "refine the search"\n   - **ALWAYS** focus on "click products to verify" rather than "search again"\n\n2. **Navigation Patterns**\n   - Avoid "browse next page" without checking current page products first\n   - Do not suggest "try different search terms" after already searching\n   - Never recommend circular navigation (search -> back -> search)\n\n3. **Product Selection**\n   - ALWAYS verify product attributes BEFORE clicking buy\n   - Check at least 3 products before selection (unless exact match)\n   - Confirm size/color options match goal requirements\n\n4. **Failure Recovery**\n   - If search returns no results: broaden keywords, don\'t restart\n   - If product unavailable: check alternatives immediately\n   - Never suggest "start over" - always make forward progress\n'
    FAILURE_PATTERNS: List[Dict[str, str]] = [{'pattern': 'infinite_search_loop', 'description': 'Searching repeatedly without examining products', 'solution': "Add constraint: 'Examine at least 3 products before searching again'"}, {'pattern': 'buy_without_verification', 'description': 'Clicking buy_now without checking product attributes', 'solution': "Add validation: 'Verify [attribute] matches goal before clicking buy_now'"}, {'pattern': 'page_flipping', 'description': 'Browsing pagination without purpose', 'solution': "Add precondition: 'Only use next page if current page has no matching products'"}]

    @classmethod
    def get_constraints(cls) -> str:
        return cls.CRITICAL_CONSTRAINTS

    @classmethod
    def get_summary(cls) -> str:
        return 'WebShop constraints: no-refine-search, verify-before-buy, no-page-flip'

    @classmethod
    def get_failure_patterns(cls) -> List[Dict[str, str]]:
        return cls.FAILURE_PATTERNS

    @classmethod
    def validate_skill_text(cls, text: str) -> tuple[bool, List[str]]:
        violations = []
        text_lower = text.lower()
        prohibited_patterns = [('refine the search', 'Add specific keywords to initial query instead'), ('go back to search', 'Continue with current results or examine products'), ('start over', 'Make progress with available information'), ('try again with', 'Work with current search results')]
        for pattern, suggestion in prohibited_patterns:
            if pattern in text_lower:
                violations.append(f"Violation: '{pattern}' detected. Suggestion: {suggestion}")
        return (len(violations) == 0, violations)
