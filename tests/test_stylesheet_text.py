"""Reading the CSS out of an HTML page — where the laws get their input.

Every law that reads a stylesheet (`assert_components_use_container_queries`,
`assert_one_transition_declaration`) and the viewport matrix itself all start
here, and none of them can tell a page with no rules from a page whose rules
were never found. So the failure this file exists for is silent by
construction: the sweep goes green, the report looks clean, and the page was
never measured.

The trap that produced it (2026-08-10, sm64_tracker's ground-truth harness
page): a page that lifts a SIBLING page's design system at runtime, with
`source.indexOf("<style>")` written in its own JavaScript. The old reader
scanned for that literal string, found the one inside the script, and sliced
to the next `"</style>"` — also inside the script. It returned 326 characters
of JavaScript as "the stylesheet", `parse_blocks` found zero blocks in it, and
the container-query law reported the page clean without ever seeing its CSS.
"""
from uilab import css


def test_a_plain_css_file_is_returned_whole(tmp_path):
    path = tmp_path / "app.css"
    path.write_text(".card { color: red; }", encoding="utf-8")
    assert css.stylesheet_text(path) == ".card { color: red; }"


def test_a_style_tag_with_attributes_is_found(tmp_path):
    path = tmp_path / "page.html"
    path.write_text(
        '<html><head><style id="rig-style">.card { color: red; }</style>'
        '</head><body></body></html>', encoding="utf-8")
    assert ".card { color: red; }" in css.stylesheet_text(path)


def test_javascript_mentioning_the_style_tag_cannot_be_mistaken_for_css(tmp_path):
    """THE regression. The script names both tags and contains no CSS; the
    real block is below it and is the only thing that may come back."""
    path = tmp_path / "page.html"
    path.write_text(
        "<html><head>\n"
        "<script>\n"
        '  const block = source.slice(source.indexOf("<style>") + 7,\n'
        '                             source.indexOf("</style>"));\n'
        "</script>\n"
        '<style id="rig-style">\n'
        "  .rig-grid { display: grid; }\n"
        "  @media (max-width: 980px) { .rig-grid { grid-template-columns: 1fr; } }\n"
        "</style>\n"
        "</head><body></body></html>", encoding="utf-8")

    text = css.stylesheet_text(path)

    assert "source.indexOf" not in text
    assert ".rig-grid { display: grid; }" in text
    blocks = css.size_blocks(css.parse_blocks(text))
    assert [(block.kind, block.selectors) for block in blocks] == [
        ("media", [".rig-grid"])]


def test_every_style_block_is_read_not_only_the_first(tmp_path):
    """A base sheet plus an override sheet used to be half-measured, with the
    second one's rules invisible to every law."""
    path = tmp_path / "page.html"
    path.write_text(
        "<html><head>"
        "<style>@container (max-width: 400px) { .a { color: red; } }</style>"
        "<style>@media (max-width: 700px) { .b { color: blue; } }</style>"
        "</head><body></body></html>", encoding="utf-8")

    blocks = css.size_blocks(css.parse_blocks(css.stylesheet_text(path)))

    assert sorted(selector for block in blocks for selector in block.selectors) \
        == [".a", ".b"]


def test_an_html_page_with_no_style_block_falls_back_to_the_whole_file(tmp_path):
    """Unchanged behaviour, and it has to stay: a project may legitimately
    point `stylesheet` at a file that is not HTML at all."""
    path = tmp_path / "page.html"
    path.write_text("<html><body>no css here</body></html>", encoding="utf-8")
    assert css.stylesheet_text(path) == "<html><body>no css here</body></html>"
