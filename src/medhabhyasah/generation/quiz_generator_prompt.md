Return ONLY a JSON array — no prose, no markdown, no code fences.
Each element must have exactly these fields:

{
  "difficulty": "Easy" | "Medium" | "Hard",
  "type": "mcq",
  "question": "<question text — plain text, no HTML, no numbering>",
  "options": ["<A>", "<B>", "<C>", "<D>"],
  "answer": 0 | 1 | 2 | 3,
  "explanation": "<explanation>",
  "source_quote": "<verbatim sentence from reference, or empty string>"
}

Rules:
- Exactly 4 options per question
- answer is the 0-based index of the correct option (0, 1, 2, or 3)
- question, options, and explanation must be plain text only — no HTML, no markdown, no links
- Do not include question numbers in question text
- Return ONLY the JSON array, starting with [ and ending with ]
