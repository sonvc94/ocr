"""document=auto: tell which Japanese document an image is from its OCR text.

Each document has printed words (title, labels, the passport's machine-readable zone) with a weight; the document
with the highest total wins. Words printed on several documents (氏名, 住所, まで有効, 日本国…) are left out.
All documents use the same Japanese OCR, so one OCR pass is enough to decide (pipeline.extract).

When no document reaches MIN_SCORE (title not read, blurry photo…), the document is guessed from the weak evidence
left: the markers that were found plus the shape of the numbers printed (GUESS_HINTS). No evidence, or a tie → None
and pipeline.extract returns the OCR text only (never an error).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .card_core.layout import Document
from .card_core.pattern_card import jp_normalize
from .ocr.types import OcrBox

# A document needs at least this score (one title, or two labels) to be chosen at all.
MIN_SCORE = 3
# The runner-up reaching this share of the best score makes the choice uncertain.
AMBIGUOUS_RATIO = 0.75

_ = re.compile
MARKERS: dict[str, list[tuple[re.Pattern, int]]] = {
    "jp_residence": [
        (_(r"在\s*留\s*カ\s*[ー一-]?\s*ド|RESIDENCE\s*CARD", re.I), 3),
        (_(r"特\s*定\s*在\s*留"), 3),  # 特定在留カード also carries My Number wording
        (_(r"在\s*留\s*資\s*格"), 2),
        (_(r"就\s*労\s*制\s*限"), 2),
        (_(r"住\s*居\s*地"), 2),
        (_(r"在\s*留\s*期\s*間"), 1),
        (_(r"国\s*籍\s*[・·]?\s*地\s*域"), 1),
    ],
    "jp_mynumber": [
        (_(r"個\s*人\s*番\s*号\s*カ\s*[ー一-]?\s*ド|マ\s*イ\s*ナ\s*ン\s*バ\s*[ー一-]?\s*カ\s*[ー一-]?\s*ド"), 3),
        (_(r"電\s*子\s*証\s*明\s*書"), 2),
        (_(r"臓\s*器\s*提\s*供"), 1),
    ],
    "jp_driver_license": [
        (_(r"運\s*転\s*免\s*許\s*証"), 3),
        (_(r"公\s*安\s*委\s*員\s*会"), 3),
        (_(r"第\s*\d[\d\s]{10,16}\s*号"), 2),
        (_(r"免\s*許\s*の?\s*条\s*件"), 2),
        (_(r"二\s*[・·]\s*小\s*[・·]\s*原"), 1),
    ],
    "jp_passport": [
        (_(r"P[A-Z<]\s*JPN"), 3),  # MRZ line 1
        (_(r"[A-Z0-9<]{9}\s*[0-9<]\s*JPN\s*\d{6}"), 3),  # MRZ line 2
        (_(r"旅\s*券|PASSPORT", re.I), 2),
        (_(r"Passport\s*No", re.I), 2),
        (_(r"発\s*行\s*国|Issuing\s*country", re.I), 1),
        (_(r"Surname|Given\s*name", re.I), 1),
    ],
    "jp_health_insurance": [
        (_(r"被\s*保\s*険\s*者\s*証|被\s*扶\s*養\s*者\s*証|資\s*格\s*確\s*認\s*書|組\s*合\s*員\s*証|加\s*入\s*者\s*証"), 3),
        (_(r"保\s*険\s*者\s*番\s*号"), 2),
        (_(r"保\s*険\s*者\s*名\s*称|交\s*付\s*者\s*名"), 2),
        (_(r"健\s*康\s*保\s*険"), 1),
    ],
}


# Used only to guess when no document reached MIN_SCORE: values whose shape belongs to one document.
GUESS_HINTS: dict[str, list[tuple[re.Pattern, int]]] = {
    "jp_residence": [(_(r"(?<![A-Z0-9])[A-Z]{2}\s?\d{8}\s?[A-Z]{2}(?![A-Z0-9])"), 2)],  # card number AB12345678CD
    "jp_mynumber": [(_(r"個\s*人\s*番\s*号"), 1)],
    "jp_driver_license": [(_(r"(?<!\d)\d{12}(?!\d)"), 1), (_(r"運\s*転|免\s*許"), 1)],
    "jp_passport": [(_(r"(?<![A-Z0-9])[A-Z]{2}\d{7}(?![A-Z0-9])"), 1), (_(r"<<<"), 1)],
    "jp_health_insurance": [(_(r"記\s*号"), 1), (_(r"保\s*険"), 1)],
}


@dataclass
class Detection:
    document: str | None  # None when nothing was found, not even a guess
    scores: dict[str, int]
    confident: bool
    guessed: bool = False  # no document reached MIN_SCORE; `document` is the best guess from weak evidence
    guess_scores: dict[str, int] | None = None  # scores + GUESS_HINTS, when no document reached MIN_SCORE

    def to_dict(self) -> dict:
        return {
            "requested": "auto",
            "detected": self.document,
            "confident": self.confident,
            "guessed": self.guessed,
            "scores": self.scores,
            "guess_scores": self.guess_scores,
        }


def detect_document(boxes: list[OcrBox]) -> Detection:
    # Rows as the parsers see them: a title split into 2 OCR boxes ("個人番号" "カード") ends up side by side.
    text = Document(boxes, jp_normalize).text
    scores = {doc: sum(w for p, w in markers if p.search(text)) for doc, markers in MARKERS.items()}
    ranked = sorted(scores, key=scores.get, reverse=True)
    best, runner_up = scores[ranked[0]], scores[ranked[1]]
    if best >= MIN_SCORE:
        return Detection(ranked[0], scores, runner_up < best * AMBIGUOUS_RATIO)
    return _guess(text, scores)


def _guess(text: str, scores: dict[str, int]) -> Detection:
    guess = {doc: scores[doc] + sum(w for p, w in GUESS_HINTS[doc] if p.search(text)) for doc in MARKERS}
    ranked = sorted(guess, key=guess.get, reverse=True)
    if guess[ranked[0]] == 0 or guess[ranked[0]] == guess[ranked[1]]:
        return Detection(None, scores, False, guess_scores=guess)
    return Detection(ranked[0], scores, False, guessed=True, guess_scores=guess)
