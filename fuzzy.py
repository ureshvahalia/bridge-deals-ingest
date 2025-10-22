import numpy as np
import re
from rapidfuzz import fuzz, process
from collections import defaultdict, Counter
from typing import List, Dict, Tuple, Set
import string


def fuzzy_deduplicate_events(
    event_names: List[str], 
    similarity_threshold: float = 88.0,
    scorer=fuzz.WRatio,
    case_sensitive: bool = False,
    number_sensitive: bool = True
) -> Dict[str, str]:
    """
    Deduplicate a list of event names using fuzzy string matching.
    
    Args:
        event_names: List of event names that may contain duplicates/misspellings
        similarity_threshold: Minimum similarity score (0-100) to consider items as duplicates
        scorer: rapidfuzz scoring function to use (WRatio is good for general use)
        case_sensitive: If False, ignores case differences when matching
        number_sensitive: If True, treats number differences as significant
    
    Returns:
        Tuple of (unique_events, mapping) where:
        - unique_events: List of deduplicated event names
        - mapping: Dict mapping original names to their canonical versions
    """
    if not event_names:
        return [], {}, []
    
    # Remove exact duplicates and keep track of counts
    name_counts = Counter(event_names)
    unique_names = list(name_counts.keys())
    # score_list: List[Tuple[str, str, float]] = []
    
    # Create a custom scoring function that handles case and numbers
    def custom_scorer(str1: str, str2: str) -> float:
        # return _enhanced_similarity_score(str1, str2, scorer, case_sensitive, number_sensitive)
        return scorer(str1.lower().translate(str.maketrans('', '', string.digits)),
                      str2.lower().translate(str.maketrans('', '', string.digits)))
    
    # Group similar names together
    groups = []
    processed = set()
    
    for i, name in enumerate(unique_names):
        if name in processed:
            continue
            
        # Find all names similar to this one
        similar_group = [name]
        processed.add(name)
        
        for j, other_name in enumerate(unique_names[i+1:], i+1):
            if other_name in processed:
                continue
                
            similarity = custom_scorer(name, other_name)
            # score_list.append((name, other_name, similarity))
            if similarity >= similarity_threshold:
                similar_group.append(other_name)
                processed.add(other_name)
        
        groups.append(similar_group)
    
    # For each group, find the best representative name
    # unique_events = []
    mapping = {}
    
    for group in groups:
        if len(group) == 1:
            # Single item, no need to choose
            canonical_name = group[0]
        else:
            # Multiple similar names - choose the best representative
            canonical_name = _choose_best_representative(group, name_counts, custom_scorer)
        
        # unique_events.append(canonical_name)
        
        # Map all group members to the canonical name
        for name in group:
            mapping[name] = canonical_name
    
    # Create final mapping for all original names (including exact duplicates)
    final_mapping = {}
    for original_name in event_names:
        final_mapping[original_name] = mapping[original_name]
    
    # return unique_events, final_mapping, score_list
    return final_mapping


def _enhanced_similarity_score(
    str1: str, 
    str2: str, 
    scorer, 
    case_sensitive: bool = False, 
    number_sensitive: bool = True
) -> float:
    """
    Enhanced similarity scoring that handles case sensitivity and number differences.
    
    Args:
        str1, str2: Strings to compare
        scorer: Base scoring function from rapidfuzz
        case_sensitive: If False, ignores case differences
        number_sensitive: If True, treats number differences as highly significant
    
    Returns:
        Similarity score (0-100)
    """
    # If number_sensitive is True, check if numbers differ significantly
    if number_sensitive:
        numbers1 = set(re.findall(r'\d+', str1))
        numbers2 = set(re.findall(r'\d+', str2))
        
        # If they have different sets of numbers, heavily penalize the score
        if numbers1 != numbers2:
            # Still compute base similarity but apply heavy penalty
            if case_sensitive:
                base_score = scorer(str1, str2)
            else:
                base_score = scorer(str1.lower(), str2.lower())
            
            # Apply significant penalty for number differences
            # The more numbers differ, the bigger the penalty
            all_numbers = numbers1.union(numbers2)
            different_numbers = numbers1.symmetric_difference(numbers2)
            
            if all_numbers:
                number_diff_ratio = len(different_numbers) / len(all_numbers)
                penalty = min(50, number_diff_ratio * 60)  # Up to 60 point penalty
                return max(0, base_score - penalty)
            else:
                # No numbers in either string, proceed normally
                return base_score
    
    # Normal fuzzy matching
    if case_sensitive:
        return scorer(str1, str2)
    else:
        return scorer(str1.lower(), str2.lower())


def _choose_best_representative(
    group: List[str], 
    name_counts: Counter, 
    scorer_func
) -> str:
    """
    Choose the best representative name from a group of similar names.
    
    The best representative is chosen based on:
    1. Highest frequency in the original list
    2. Highest average similarity to other group members
    3. Shortest length (tie-breaker)
    """
    if len(group) == 1:
        return group[0]
    
    scores = []
    
    for candidate in group:
        # Factor 1: Frequency in original data (normalized)
        frequency_score = name_counts[candidate]
        
        # Factor 2: Average similarity to other group members
        similarities = []
        for other in group:
            if other != candidate:
                similarities.append(scorer_func(candidate, other))
        avg_similarity = np.mean(similarities) if similarities else 0
        
        # Factor 3: Length penalty (shorter is better, normalized)
        length_penalty = 1.0 / (len(candidate) + 1)  # +1 to avoid division by zero
        
        # Combine scores (you can adjust weights as needed)
        total_score = (
            frequency_score * 2.0 +      # Weight frequency highly
            avg_similarity * 1.0 +       # Similarity to group
            length_penalty * 0.1         # Slight preference for shorter names
        )
        
        scores.append((total_score, candidate))
    
    # Return the candidate with the highest score
    return max(scores)[1]


def analyze_deduplication(
    original_names: List[str], 
    unique_events: List[str], 
    mapping: Dict[str, str]
) -> None:
    """Print analysis of the deduplication results."""
    print(f"Original events: {len(original_names)}")
    print(f"Unique events after deduplication: {len(unique_events)}")
    print(f"Reduction: {len(original_names) - len(unique_events)} duplicates removed")
    print(f"Reduction percentage: {((len(original_names) - len(unique_events)) / len(original_names)) * 100:.1f}%")
    
    # Show groups that were merged
    reverse_mapping = defaultdict(list)
    for orig, canonical in mapping.items():
        reverse_mapping[canonical].append(orig)
    
    merged_groups = {k: v for k, v in reverse_mapping.items() if len(set(v)) > 1}
    
    if merged_groups:
        print(f"\nGroups that were merged ({len(merged_groups)}):")
        for canonical, originals in merged_groups.items():
            unique_originals = list(set(originals))
            if len(unique_originals) > 1:
                print(f"  '{canonical}' ← {unique_originals}")


# Example usage and test
if __name__ == "__main__":
    # Sample event names with intentional duplicates and misspellings
    sample_events = [
        "Summer Music Festival",
        "SUMMER MUSIC FESTIVAL",  # case difference
        "Summer Music Festiva",   # typo
        "Summer Music Festival",  # exact duplicate
        "Sumer Music Festival",   # typo
        "12th Cap Gemini World Top Tournament 1998",
        "13th Cap Gemini World Top Tournament 1999",  # different numbers
        "12th Cap Gemini World Top Tournament 1998",  # exact duplicate
        "12th Cap Gemini World Top Tournment 1998",   # typo but same numbers
        "Winter Concert Series",
        "winter concert series",  # case difference
        "Winter Concert Serie",   # typo
        "Annual Charity Run 2023",
        "Annual Charity Run 2024",  # different year
        "Annual Charity Run 2023",  # exact duplicate
        "Anual Charity Run 2023",   # typo but same year
    ]
    
    print("Sample event names:")
    for i, event in enumerate(sample_events, 1):
        print(f"  {i:2d}. {event}")
    
    print("\n" + "="*60)
    
    # Perform deduplication with case-insensitive, number-sensitive matching
    unique_events, mapping, _ = fuzzy_deduplicate_events(
        sample_events, 
        similarity_threshold=85.0,
        case_sensitive=False,    # Ignore case differences
        number_sensitive=True    # Treat number differences as significant
    )
    
    # Show results
    print("\nUnique events after deduplication:")
    for i, event in enumerate(sorted(unique_events), 1):
        print(f"  {i:2d}. {event}")
    
    print("\n" + "="*60)
    analyze_deduplication(sample_events, unique_events, mapping)
    
    print("\nMapping from original to canonical names:")
    for original, canonical in mapping.items():
        if original != canonical:
            print(f"  '{original}' → '{canonical}'")