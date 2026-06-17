"""
Project name normalization.

When the LLM extracts a "project" field per document (Step 2), slightly
different phrasings of the same project ("API Hub Search" vs "API Hub
Search Tool") would otherwise be treated as separate projects in gap
analysis -- splitting one project's documentation coverage across two
buckets and producing misleading gaps.

This module fuzzy-matches a newly extracted project name against the set
of canonical names already seen, and maps it to an existing one if it's a
close enough match. Every match (or non-match) is logged so you can spot-check
the decisions later -- this is intentionally simple, not foolproof.
"""
from rapidfuzz import fuzz

# Below this score, treat the name as genuinely new rather than a variant.
# 80 catches common variants like adding/dropping a suffix word
# ("API Hub Search" vs "API Hub Search Tool" scores ~85) while still
# rejecting genuinely unrelated project names (which scored ~25 in testing).
MATCH_THRESHOLD = 80


def normalize_project_name(new_name: str, known_names: list[str]) -> tuple[str, bool]:
    """
    Compare new_name against known_names. Returns (canonical_name, was_merged).

    - If new_name matches an existing name closely enough, returns that
      existing name and was_merged=True.
    - Otherwise returns new_name unchanged and was_merged=False (it becomes
      a new canonical name going forward).

    known_names should come from db_writer.get_all_projects() -- the set of
    project names already stored in structured_knowledge.
    """
    if not new_name or not new_name.strip():
        return new_name, False

    if not known_names:
        return new_name, False

    best_match = None
    best_score = 0

    for existing in known_names:
        # token_sort_ratio handles word-order differences and partial overlaps
        # better than a plain ratio would (e.g. "Search Tool: API Hub" vs "API Hub Search Tool")
        score = fuzz.token_sort_ratio(new_name.lower(), existing.lower())
        if score > best_score:
            best_score = score
            best_match = existing

    if best_score >= MATCH_THRESHOLD:
        if best_match != new_name:
            print(
                f"  [normalize] '{new_name}' -> '{best_match}' "
                f"(similarity {best_score:.0f}, merged)"
            )
        return best_match, (best_match != new_name)

    return new_name, False
