from app.evaluation.rag import evaluate_rag_records, stable_rag_dataset_hash


def test_rag_evaluation_metrics_and_hash_are_deterministic() -> None:
    records = [
        {
            "expectedSourceIds": ["one", "two"],
            "returnedSourceIds": ["one"],
            "requiredPoints": ["asyncio", "gather"],
            "answer": "asyncio gather объединяет задачи",
            "citationValidationPassed": True,
            "expectedInsufficient": False,
            "insufficientContext": False,
        },
        {
            "expectedSourceIds": [],
            "returnedSourceIds": [],
            "requiredPoints": [],
            "answer": "Недостаточно информации",
            "citationValidationPassed": True,
            "expectedInsufficient": True,
            "insufficientContext": True,
        },
    ]
    metrics = evaluate_rag_records(records)
    assert metrics.source_recall == 0.75
    assert metrics.citation_validity == 1
    assert metrics.key_point_coverage == 1
    assert metrics.insufficient_context_accuracy == 1
    assert stable_rag_dataset_hash(records) == stable_rag_dataset_hash(records)


def test_rag_evaluation_rejects_empty_dataset() -> None:
    try:
        evaluate_rag_records([])
    except ValueError as error:
        assert "хотя бы одну" in str(error)
    else:
        raise AssertionError("empty evaluation must be rejected")
