from dataclasses import dataclass


@dataclass
class StudentScore:
    name: str
    score: int


def normalize_scores(items: list[StudentScore]) -> list[StudentScore]:
    if not items:
        return []

    max_score = max(item.score for item in items)
    if max_score <= 0:
        return [StudentScore(name=item.name, score=0) for item in items]

    normalized: list[StudentScore] = []
    for item in items:
        scaled = int(item.score / max_score * 100)
        normalized.append(StudentScore(name=item.name, score=scaled))
    return normalized


def summarize_scores(items: list[StudentScore]) -> dict[str, object]:
    normalized = normalize_scores(items)
    if not normalized:
        return {
            "count": 0,
            "average": 0,
            "passed": [],
            "failed": [],
            "top_student": None,
        }

    total = 0
    passed: list[str] = []
    failed: list[str] = []
    top_student = normalized[0]

    for item in normalized:
        total += item.score
        if item.score >= 60:
            passed.append(item.name)
        else:
            failed.append(item.name)

        if item.score > top_student.score:
            top_student = item

    average = round(total / len(normalized), 2)
    return {
        "count": len(normalized),
        "average": average,
        "passed": passed,
        "failed": failed,
        "top_student": {
            "name": top_student.name,
            "score": top_student.score,
        },
    }


def main() -> None:
    students = [
        StudentScore("Alice", 72),
        StudentScore("Bob", 54),
        StudentScore("Cindy", 91),
        StudentScore("David", 66),
        StudentScore("Eva", 48),
    ]
    result = summarize_scores(students)
    print("Score summary:")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
