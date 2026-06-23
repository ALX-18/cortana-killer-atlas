"""
Sprint v5.2 clôture — AXE 1
Tests heuristiques memory/redo élargies + fuzzy Levenshtein.

Bug terrain : "refait" (typo de "refais") tombait en conversation → timeout 60s.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from core.intent_classifier import (
    IntentClassifier,
    _levenshtein,
    _REDO_FUZZY_VERBS,
)


CTX = {
    "foreground_window": "",
    "cpu_percent": 5,
    "ram_percent": 30,
    "top_processes": [],
}


@pytest.fixture
def clf():
    return IntentClassifier()


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #

class TestLevenshtein:
    def test_identical(self):
        assert _levenshtein("refais", "refais") == 0

    def test_one_substitution(self):
        # "refait" vs "refais" — single char swap (s→t)
        assert _levenshtein("refait", "refais") == 1

    def test_one_insertion(self):
        assert _levenshtein("rrefait", "refait") == 1

    def test_two_edits(self):
        # "refoit" vs "refais" — 2 edits (o→a, i→s positionally)
        assert _levenshtein("refoit", "refais") <= 2

    def test_empty_string(self):
        assert _levenshtein("", "abc") == 3
        assert _levenshtein("abc", "") == 3

    def test_completely_different(self):
        assert _levenshtein("ouvre", "refais") >= 4


# --------------------------------------------------------------------------- #
#  AXE 1 — Cas explicitement listés dans le brief de clôture
# --------------------------------------------------------------------------- #

class TestExpandedRedoHeuristics:
    def test_refait_with_t(self, clf):
        """The typo from the field campaign — must classify as memory/redo."""
        result = clf.classify("refait", CTX)
        assert result.category == "memory"
        assert result.verb == "redo"

    def test_relance(self, clf):
        result = clf.classify("relance", CTX)
        assert result.category == "memory"
        assert result.verb == "redo"

    def test_repete_accented(self, clf):
        result = clf.classify("répète", CTX)
        assert result.category == "memory"
        assert result.verb == "redo"

    def test_repete_no_accent(self, clf):
        result = clf.classify("repete", CTX)
        assert result.category == "memory"
        assert result.verb == "redo"

    def test_encore_une_fois(self, clf):
        result = clf.classify("encore une fois", CTX)
        assert result.category == "memory"
        assert result.verb == "redo"

    def test_a_nouveau(self, clf):
        result = clf.classify("à nouveau", CTX)
        assert result.category == "memory"
        assert result.verb == "redo"


# --------------------------------------------------------------------------- #
#  AXE 1 — fuzzy fallback (Levenshtein ≤ 2)
# --------------------------------------------------------------------------- #

class TestFuzzyRedoMatch:
    def test_typo_with_double_letter(self, clf):
        result = clf.classify("rrefait", CTX)
        assert result.category == "memory"
        assert result.verb == "redo"

    def test_typo_one_substitution(self, clf):
        # "refoit" vs "refais" → distance 2
        result = clf.classify("refoit", CTX)
        assert result.category == "memory"
        assert result.verb == "redo"

    def test_typo_relence_for_relance(self, clf):
        # "relence" vs "relance" → distance 1
        result = clf.classify("relence", CTX)
        assert result.category == "memory"
        assert result.verb == "redo"


# --------------------------------------------------------------------------- #
#  Non-régression : les heuristiques originales doivent toujours marcher
# --------------------------------------------------------------------------- #

class TestRedoBackwardCompat:
    def test_refais_still_works(self, clf):
        result = clf.classify("refais", CTX)
        assert result.category == "memory"
        assert result.verb == "redo"

    def test_encore_still_works(self, clf):
        result = clf.classify("encore", CTX)
        assert result.category == "memory"
        assert result.verb == "redo"

    def test_redo_english(self, clf):
        result = clf.classify("redo", CTX)
        assert result.category == "memory"
        assert result.verb == "redo"


# --------------------------------------------------------------------------- #
#  Non-régression : autres catégories ne doivent PAS être faussement matchées
# --------------------------------------------------------------------------- #

class TestNoFalsePositives:
    def test_short_word_not_fuzzy_matched(self, clf):
        """Short words (<4 chars) skipped to avoid false positives."""
        # "tab" should NOT trigger redo (although Levenshtein from short verb might)
        result = clf.classify("tab", CTX)
        assert result.category != "memory" or result.verb != "redo"

    def test_unrelated_command_not_redo(self, clf):
        result = clf.classify("ouvre le bloc-notes", CTX)
        assert result.verb != "redo"

    def test_click_command_not_redo(self, clf):
        result = clf.classify("clique sur Bibliothèque dans Steam", CTX)
        assert result.verb != "redo"


# --------------------------------------------------------------------------- #
#  AXE 1 — fuzzy verbs constant exposed
# --------------------------------------------------------------------------- #

class TestRedoFuzzyVerbsExposed:
    def test_constant_includes_canonical_forms(self):
        assert "refais" in _REDO_FUZZY_VERBS
        assert "relance" in _REDO_FUZZY_VERBS
        assert "redo" in _REDO_FUZZY_VERBS
