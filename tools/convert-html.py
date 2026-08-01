#!/usr/bin/env python3
"""
Convert HTML to Elementor JSON.

Usage:
    python tools/convert-html.py page.html
    python tools/convert-html.py page.html --auto-layout container
    python tools/convert-html.py page.html --custom-css out.css --js-hints out.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from html.parser import HTMLParser
from collections import defaultdict

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"
SCHEMA_FILE = DATA_DIR / "elementor-schema.json"

# Load schema for control validation
_schema: dict | None = None

def schema() -> dict:
    global _schema
    if _schema is None:
        _schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    return _schema


class HTMLAnalyzer(HTMLParser):
    """Parse HTML and build an AST-like structure."""

    def __init__(self):
        super().__init__()
        self.root = {"tag": "body", "attrs": {}, "children": [], "content": ""}
        self.stack = [self.root]
        self.css_inline = {}
        self.js_warnings = []
        self.has_animations = False
        self.has_hover = False

    def handle_starttag(self, tag: str, attrs: list):
        # Detect JS dependencies
        attrs_dict = dict(attrs)
        if any(k.startswith("on") for k in attrs_dict.keys()):
            self.js_warnings.append(f"Element <{tag}> has event handler: {', '.join(k for k in attrs_dict.keys() if k.startswith('on'))}")

        # Track animations in class/style
        class_str = attrs_dict.get("class", "")
        style_str = attrs_dict.get("style", "")
        if re.search(r"animate|transition|keyframe", class_str + style_str, re.I):
            self.has_animations = True
            self.js_warnings.append(f"<{tag}> class='{class_str}' has animation — may need JS")
        if ":hover" in style_str:
            self.has_hover = True

        node = {
            "tag": tag,
            "attrs": attrs_dict,
            "children": [],
            "content": "",
        }
        self.stack[-1]["children"].append(node)

        # Self-closing tags don't need stack manipulation
        if tag not in ("br", "hr", "img", "input", "meta", "link"):
            self.stack.append(node)

    def handle_endtag(self, tag: str):
        if tag not in ("br", "hr", "img", "input", "meta", "link") and len(self.stack) > 1:
            self.stack.pop()

    def handle_data(self, data: str):
        text = data.strip()
        if text and self.stack:
            self.stack[-1]["content"] += text + " "


class HTMLToElementor:
    """Convert parsed HTML to Elementor JSON structure."""

    def __init__(self, html_content: str):
        self.analyzer = HTMLAnalyzer()
        self.analyzer.feed(html_content)
        self.tree = self.analyzer.root
        self.css_rules = {}
        self.js_hints = self.analyzer.js_warnings
        self.element_id_counter = 0

    def gen_id(self) -> str:
        """Generate unique 7-char hex ID."""
        self.element_id_counter += 1
        return f"{self.element_id_counter:06x}"

    def detect_widget_type(self, node: dict) -> tuple[str, str]:
        """Infer Elementor widget from HTML tag/structure.
        Returns: (widget_type, layout_hint) where layout_hint is 'row', 'grid', or 'column'
        """
        tag = node["tag"].lower()
        classes = node["attrs"].get("class", "").lower()
        style = node["attrs"].get("style", "").lower()

        # Map HTML tags → Elementor widgets
        mapping = {
            "h1": "heading",
            "h2": "heading",
            "h3": "heading",
            "h4": "heading",
            "h5": "heading",
            "h6": "heading",
            "p": "text-editor",
            "img": "image",
            "a": "button",  # standalone links → buttons
            "button": "button",
            "form": "form",
            "video": "video",
            "iframe": "video",  # some iframes are videos
            "ul": "text-editor",  # fallback: list → text
            "ol": "text-editor",
            "table": "text-editor",  # fallback
        }

        # Text/content elements
        if tag in mapping:
            return mapping[tag], "inline"

        # Detect card layout — use container, not icon-box (which doesn't accept children)
        if "card" in classes or (
            len(node["children"]) > 2 and
            any(c["tag"].lower() in ("img", "h1", "h2", "h3", "h4", "h5") for c in node["children"])
        ):
            return "container", "column"  # card as flex column container

        # Detect layout containers (section, div, main, article)
        if tag in ("section", "div", "main", "article"):
            # Detect grid layout
            if "grid" in classes or "display: grid" in style:
                return "container", "grid"
            # Detect flex row
            if "row" in classes or ("display: flex" in style and "flex-direction: row" not in style):
                layout = self._infer_flex_direction(node)
                return "container", layout
            # Multi-column divs (e.g., 3 cards in a row)
            if self._has_multi_columns(node):
                return "container", "row"
            # Default: vertical stack
            return "container", "column"

        return "container", "column"  # safe fallback

    def _infer_flex_direction(self, node: dict) -> str:
        """Determine flex-direction from style or class."""
        style = node["attrs"].get("style", "").lower()
        classes = node["attrs"].get("class", "").lower()

        if "flex-direction: column" in style or "column" in classes:
            return "column"
        if "flex-direction: row" in style or "row" in classes:
            return "row"
        if "grid-template-columns" in style:
            return "grid"
        return "row"  # flex defaults to row

    def _has_multi_columns(self, node: dict) -> bool:
        """Check if node appears to be a multi-column layout."""
        classes = node["attrs"].get("class", "").lower()
        style = node["attrs"].get("style", "").lower()

        if "row" in classes or "grid" in classes or "flex" in classes:
            return True
        if "display: grid" in style or "grid-template-columns" in style:
            return True
        if "display: flex" in style and "flex-direction: column" not in style:
            return True

        # Heuristic: has 2+ child divs side-by-side
        divs = [c for c in node["children"] if c["tag"].lower() in ("div", "li")]
        return len(divs) >= 2

    def to_elementor(self, node: dict, depth: int = 0) -> dict | None:
        """Recursively convert HTML node to Elementor element.
        Returns None if node should be skipped.
        """
        # Skip non-rendered elements
        if node["tag"].lower() in ("script", "style", "meta", "link", "head", "title"):
            return None

        widget_type, layout_hint = self.detect_widget_type(node)
        elem_id = self.gen_id()

        settings = self._extract_settings(node, widget_type)

        # Apply layout settings for containers
        if widget_type == "container":
            settings["container_type"] = "flex"
            if layout_hint == "row":
                settings["flex_direction"] = "row"
                settings["flex_wrap"] = "wrap"
            elif layout_hint == "grid":
                settings["container_type"] = "grid"
                settings["grid_columns_grid"] = {"unit": "fr", "size": self._infer_grid_columns(node), "sizes": []}
            else:
                settings["flex_direction"] = "column"

        elem = {
            "id": elem_id,
            "elType": "widget" if widget_type != "container" else "container",
            "widgetType": widget_type if widget_type != "container" else None,
            "settings": settings,
            "elements": [],
        }

        # Recursively convert children
        for child in node["children"]:
            child_elem = self.to_elementor(child, depth + 1)
            if child_elem is not None:
                elem["elements"].append(child_elem)

        return elem

    def _infer_grid_columns(self, node: dict) -> int:
        """Infer number of grid columns from CSS or children count."""
        style = node["attrs"].get("style", "").lower()

        # Parse grid-template-columns
        match = re.search(r"grid-template-columns:\s*repeat\((\d+)", style)
        if match:
            return int(match.group(1))

        # Count child divs (heuristic)
        divs = [c for c in node["children"] if c["tag"].lower() == "div"]
        if len(divs) >= 3:
            return 3
        elif len(divs) >= 2:
            return 2
        return 1

    def _extract_settings(self, node: dict, widget_type: str) -> dict:
        """Extract settings from HTML node."""
        settings = {}
        attrs = node["attrs"]
        content = node["content"].strip()

        # Common settings
        if content:
            if widget_type == "heading":
                settings["title"] = content
                settings["header_size"] = "h2"
            elif widget_type == "text-editor":
                settings["editor"] = f"<p>{content}</p>"
            elif widget_type == "button":
                settings["text"] = content
                settings["link"] = {"url": attrs.get("href", "#")}

        if widget_type == "image" and "src" in attrs:
            settings["image"] = {"url": attrs["src"]}

        # Extract inline styles
        style = attrs.get("style", "")
        if style:
            self._parse_inline_styles(style, settings, widget_type)

        # Extract class-based styling
        classes = attrs.get("class", "").split()
        for cls in classes:
            if "text-" in cls or "color" in cls:
                self.js_hints.append(f"Class '{cls}' may contain styling — check CSS")

        return settings

    def _parse_inline_styles(self, style: str, settings: dict, widget_type: str):
        """Parse inline CSS and map to Elementor controls."""
        # Simple regex-based parsing (not exhaustive)
        pairs = re.findall(r"([a-z-]+):\s*([^;]+)", style, re.I)

        for prop, value in pairs:
            prop = prop.strip().lower()
            value = value.strip()

            # Map CSS → Elementor settings
            if "background" in prop and "color" in prop:
                settings["background_background"] = "classic"
                settings["background_color"] = value
            elif "color" in prop and "text" not in prop:
                settings["text_color"] = value
            elif "font-size" in prop:
                # Extract numeric value
                match = re.search(r"(\d+)", value)
                if match:
                    settings["title_font_size"] = {"unit": "px", "size": match.group(1)}
            elif "width" in prop:
                match = re.search(r"(\d+)", value)
                if match:
                    settings["width"] = {"unit": "px", "size": match.group(1)}
            elif "margin" in prop or "padding" in prop:
                self.js_hints.append(f"Inline {prop}: {value} — may need manual adjustment in Elementor")

    def to_json(self) -> str:
        """Convert to Elementor JSON."""
        # Build top-level structure (list of containers)
        page = []
        for child in self.tree["children"]:
            elem = self.to_elementor(child)
            if elem is not None:
                page.append(elem)

        return json.dumps(page, indent=2, ensure_ascii=False)

    def get_css(self) -> str:
        """Extract CSS that needs manual tuning."""
        lines = [
            "/* Extracted CSS — tune and apply as custom CSS in Elementor */",
            "/* Pay attention to animations, hover effects, and responsive rules */",
            "",
        ]

        # Collect inline styles
        styles_seen = set()
        def collect_styles(node):
            style = node["attrs"].get("style", "")
            if style and style not in styles_seen:
                styles_seen.add(style)
                lines.append(f"/* From {node['tag']} {node['attrs'].get('class', '')} */")
                lines.append(f"{style}")
                lines.append("")

        def traverse(node):
            collect_styles(node)
            for child in node["children"]:
                traverse(child)

        traverse(self.tree)
        return "\n".join(lines)

    def get_js_hints(self) -> str:
        """Generate JS warnings/hints."""
        lines = [
            "# JavaScript & Advanced Features Detected",
            "",
            "The following HTML features need manual code/customization in Elementor:",
            "",
        ]

        if not self.js_hints:
            lines.append("✓ No JS detected — page is static HTML.")
        else:
            for i, hint in enumerate(self.js_hints, 1):
                lines.append(f"{i}. **{hint}**")
                lines.append("   → Add custom code block or Motion FX in Elementor")
                lines.append("")

        if self.analyzer.has_animations:
            lines.append("### Animations Detected")
            lines.append("Consider using Elementor's **Motion FX** or custom CSS `@keyframe` in code block.")
            lines.append("")

        if self.analyzer.has_hover:
            lines.append("### Hover Effects")
            lines.append("Add `:hover` styles to custom CSS section or use Element's built-in hover controls.")
            lines.append("")

        lines.append("### Next Steps")
        lines.append("1. Upload `page.json` to WordPress with `tools/apply-page.php`")
        lines.append("2. Apply `custom.css` as custom CSS in page settings")
        lines.append("3. Add any missing JS in code blocks")

        return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(
        description="Convert HTML to Elementor JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("html_file", help="path to HTML file")
    p.add_argument("--output", "-o", help="output JSON file (default: <name>.json)")
    p.add_argument("--custom-css", help="extract CSS to file")
    p.add_argument("--js-hints", help="output JS/feature hints to file")
    p.add_argument("--auto-layout", choices=["container", "flex"], default="container",
                   help="default layout for divs")

    args = p.parse_args()

    html_path = Path(args.html_file)
    if not html_path.exists():
        print(f"❌ File not found: {html_path}", file=sys.stderr)
        sys.exit(1)

    # Read HTML
    html_content = html_path.read_text(encoding="utf-8")

    # Convert
    print("📖 Parsing HTML...")
    converter = HTMLToElementor(html_content)

    # Output JSON
    output_path = Path(args.output) if args.output else html_path.with_suffix(".json")
    json_str = converter.to_json()
    output_path.write_text(json_str + "\n", encoding="utf-8")
    print(f"✓ Written: {output_path}")

    # Output CSS if requested
    if args.custom_css:
        css_path = Path(args.custom_css)
        css_path.write_text(converter.get_css(), encoding="utf-8")
        print(f"✓ CSS extracted: {css_path}")

    # Output JS hints if requested
    if args.js_hints:
        hints_path = Path(args.js_hints)
        hints_path.write_text(converter.get_js_hints(), encoding="utf-8")
        print(f"✓ JS hints: {hints_path}")

    print("\n📋 Summary:")
    print(f"  HTML elements: {converter.element_id_counter}")
    print(f"  JS features detected: {len(converter.js_hints)}")
    print(f"  Next: python tools/validate-page.py {output_path}")


if __name__ == "__main__":
    main()
