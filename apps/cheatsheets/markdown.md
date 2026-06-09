# Markdown Cheatsheet

## Headings

```md
# Heading 1
## Heading 2
### Heading 3
#### Heading 4
```

---

## Text Formatting

```md
**bold**
*italic*
***bold italic***
~~strikethrough~~
`inline code`
```

Result:

| Markdown     | Meaning       |
| ------------ | ------------- |
| `**text**`   | Bold          |
| `*text*`     | Italic        |
| `***text***` | Bold + italic |
| `~~text~~`   | Strikethrough |
| `` `code` `` | Inline code   |

---

## Paragraphs and Line Breaks

```md
This is one paragraph.

This is another paragraph.
```

Line break:

```md
First line  
Second line
```

Use two spaces at the end of a line for a manual line break.

---

## Lists

### Bullet List

```md
- Item one
- Item two
  - Nested item
  - Nested item
```

### Numbered List

```md
1. First
2. Second
3. Third
```

### Task List

```md
- [x] Done task
- [ ] Pending task
- [ ] Another task
```

---

## Links

```md
[OpenAI](https://openai.com)
```

Reference-style link:

```md
[OpenAI][openai-link]

[openai-link]: https://openai.com
```

---

## Images

```md
![Alt text](image.png)
```

With URL:

```md
![Cat](https://example.com/cat.png)
```

---

## Code Blocks

Inline code:

```md
Use `print()` to output text.
```

Code block:

````md
```python
print("Hello")
```
````

Shell example:

````md
```bash
uv run python main.py
```
````

---

## Blockquotes

```md
> This is a quote.
> It can span multiple lines.
```

Nested quote:

```md
> Outer quote
>> Inner quote
```

---

## Tables

```md
| Name | Age | Role |
|---|---:|---|
| Alice | 30 | Admin |
| Bob | 25 | User |
```

Alignment:

| Syntax  | Meaning            |
| ------- | ------------------ |
| `---`   | Left/default align |
| `:---`  | Left align         |
| `---:`  | Right align        |
| `:---:` | Center align       |

Example:

```md
| Left | Center | Right |
|:---|:---:|---:|
| A | B | C |
```

---

## Horizontal Rule

```md
---
```

Also works:

```md
***
___
```

---

## Escaping Characters

Use backslash `\` to show Markdown characters literally.

```md
\*not italic\*
\# not a heading
\[not a link\]
```

---

## HTML in Markdown

Many Markdown renderers support basic HTML.

```md
<br>

<span style="color:red">Red text</span>

<div>
  Custom block
</div>
```

Use sparingly. Some platforms block or sanitize HTML.

---

## Footnotes

```md
Here is a sentence with a footnote.[^1]

[^1]: This is the footnote text.
```

Support depends on the Markdown renderer.

---

## Definition Lists

```md
Term
: Definition
```

Support depends on the Markdown renderer.

---

## Collapsible Section

```md
<details>
<summary>Click to expand</summary>

Hidden content goes here.

</details>
```

---

## Badges

```md
![Status](https://img.shields.io/badge/status-active-brightgreen)
```

Common in README files.

---

## README Structure

````md
# Project Name

Short project description.

## Features

- Feature one
- Feature two

## Installation

```bash
uv sync
````

## Usage

```bash
uv run python main.py
```

## Configuration

Explain settings here.

## License

MIT

````

---

## Common Patterns

### Warning / Note Block

```md
> **Note:** This is useful information.
````

```md
> **Warning:** This action cannot be undone.
```

### File Tree

```md
project/
├── src/
│   └── app.py
├── tests/
└── pyproject.toml
```

### Command + Explanation

````md
```bash
uv add requests
````

Adds the `requests` package to the project.

```

---

## Quick Reference

| Task | Markdown |
|---|---|
| Heading | `# Title` |
| Bold | `**text**` |
| Italic | `*text*` |
| Inline code | `` `code` `` |
| Code block | Triple backticks |
| Link | `[text](url)` |
| Image | `![alt](url)` |
| Bullet | `- item` |
| Numbered list | `1. item` |
| Task | `- [ ] task` |
| Quote | `> quote` |
| Table | `| A | B |` |
| Divider | `---` |
| Escape | `\*literal\*` |
```
