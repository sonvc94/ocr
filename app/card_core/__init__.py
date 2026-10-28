"""What every card parser shares: rows of text from OCR boxes, the Field result type, OCR quality,
and locating a card template in the image to read fields by position (mode=zone/hybrid).

Nothing here knows a card's wording: label patterns, normalization and field extraction are passed
in by each card package (residence_card has templates; the other Japanese documents use pattern_card.py).
"""
