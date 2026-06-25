from app.services.ai.classifier import classify_rule_based


def test_classifier_detects_premium_budget() -> None:
    result = classify_rule_based("Ищу дом до 100 млн рублей")
    assert result.intent == "premium_budget"
    assert result.urgency == "high"


def test_classifier_detects_legal_question() -> None:
    result = classify_rule_based("Можно купить на маткапитал?")
    assert result.intent == "legal_question"


def test_classifier_detects_copywriting() -> None:
    result = classify_rule_based("Нужно премиальное описание дома")
    assert result.intent == "copywriting"

