import unittest
from pathlib import Path

from core.lab.todo import parse_todo_markdown


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class StudioTodoTests(unittest.TestCase):
    def test_parses_sections_ids_priorities_and_completion(self):
        result = parse_todo_markdown("""# Demo TODO

## P0 · Blockers
- [ ] `BASE-001` Fix the blocker.

## Completed
- [x] `BASE-002` Done.
""")
        self.assertEqual("Demo TODO", result["title"])
        self.assertEqual(2, result["total"])
        self.assertEqual(1, result["open"])
        self.assertEqual(1, result["completed"])
        self.assertEqual("BASE-001", result["items"][0]["id"])
        self.assertNotIn("`", result["items"][0]["text"])
        self.assertEqual("P0", result["items"][0]["priority"])
        self.assertEqual("P0 · Blockers", result["items"][0]["section"])

    def test_ignores_checkbox_examples_inside_fenced_code(self):
        result = parse_todo_markdown("""# Demo

```md
- [ ] `EXAMPLE-001` Not a real task.
```

## Work
- [ ] `REAL-001` Real task.
""")
        self.assertEqual(1, result["total"])
        self.assertEqual("REAL-001", result["items"][0]["id"])

    def test_project_planning_docs_stay_focused(self):
        todo_text = (PROJECT_ROOT / "docs" / "planning" / "TODO.md").read_text(
            encoding="utf-8"
        )
        todo = parse_todo_markdown(todo_text)

        self.assertLessEqual(todo["open"], 12)
        self.assertEqual(todo["total"], todo["open"])
        task_ids = [item["id"] for item in todo["items"]]
        self.assertEqual(len(task_ids), len(set(task_ids)))

        roadmap_text = (
            PROJECT_ROOT / "docs" / "planning" / "ROADMAP.md"
        ).read_text(encoding="utf-8")
        roadmap_checkboxes = [
            line for line in roadmap_text.splitlines() if line.startswith(("- [ ]", "- [x]", "- [X]"))
        ]
        self.assertEqual([], roadmap_checkboxes)


if __name__ == "__main__":
    unittest.main()
