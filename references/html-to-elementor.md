# HTML to Elementor: Three Ways to Build Pages

This guide shows how to convert any page description (HTML, natural language, or screenshot) into an Elementor page without opening the visual editor.

## Stage 1: HTML Files

**Input:** `.html` file (Webly export, Figma export-to-HTML, any website saved locally)

```bash
python tools/convert-html.py page.html \
  --custom-css out.css \
  --js-hints out-hints.md
```

**Output:**
- `page.json` — valid Elementor `_elementor_data`, ready to upload
- `out.css` — styles needing manual Elementor tuning (gradients, animations, hover)
- `out-hints.md` — JS features you need to add code for

**How it works:**
1. Parses HTML into a tree
2. Infers Elementor widget types from tags/classes (h1→heading, section→container, etc.)
3. Detects layouts: grid (CSS Grid), flex row (3+ columns), flex column (default)
4. Extracts inline styles and marks them for custom CSS
5. Detects JS (event handlers, animations, hover effects) and flags them

**Supports:**
- ✅ Multi-column grids (3-column cards)
- ✅ Flexbox layouts
- ✅ Responsive classes
- ✅ Inline styles (extracted to CSS file)
- ⚠️  Animations (flagged for manual code)
- ⚠️  Event handlers (flagged for manual code)

**Example:**

Input HTML:
```html
<section class="hero" style="background: linear-gradient(...)">
  <h1>Welcome</h1>
  <p>Get started today</p>
  <a href="#" class="btn">Sign Up</a>
</section>

<section class="features">
  <div class="card">
    <h3>Fast</h3>
    <p>Lightning quick</p>
  </div>
  <div class="card">...</div>
  <div class="card">...</div>
</section>
```

Output JSON structure:
```json
[
  {
    "id": "a1b2c3d",
    "elType": "container",
    "settings": {
      "container_type": "flex",
      "flex_direction": "column",
      "background_color": "linear-gradient(...)"
    },
    "elements": [
      { "elType": "widget", "widgetType": "heading", "settings": { "title": "Welcome" } },
      { "elType": "widget", "widgetType": "text-editor", "settings": { "editor": "<p>Get started</p>" } },
      { "elType": "widget", "widgetType": "button", "settings": { "text": "Sign Up" } }
    ]
  },
  {
    "id": "e4f5a6b",
    "elType": "container",
    "settings": { "flex_direction": "row", "flex_wrap": "wrap" },
    "elements": [
      // 3 card containers...
    ]
  }
]
```

Then upload:
```bash
python tools/validate-page.py page.json --target free
wp eval-file tools/apply-page.php <post_id> page.json
```

---

## Stage 2: Natural Language Description

**Input:** Text description (no coding needed)

```bash
python tools/from-description.py "
- Hero section: large title + subtitle + gradient background + CTA button
- 3-column feature cards: icon + title + description
- Newsletter signup form
- Footer with social links
"
```

**How it works:**
1. Sends description to Claude Opus (smart reasoning)
2. Claude understands page structure
3. Claude generates valid Elementor JSON directly
4. Returns ready-to-use JSON

**What Claude handles:**
- ✅ Layout structure (hero, grid, sections)
- ✅ Widget selection (heading, button, form, etc.)
- ✅ Basic styling (colors, padding, container types)
- ✅ Responsive behavior (flex-direction, wrap)
- ⚠️  Complex animations (returns placeholder, you add code)
- ⚠️  Custom styling (returns basic, you tune in Elementor)

**Example:**

```bash
python tools/from-description.py "
Tall hero with gradient background, centered title and CTA.
Below: 4-column product grid with images.
Footer: simple text and links
" --output hero-grid.json

python tools/validate-page.py hero-grid.json
wp eval-file tools/apply-page.php 123 hero-grid.json
```

---

## Stage 3: Screenshots / Figma (Future)

**Input:** Screenshot or Figma design URL

```bash
# Vision-based (not yet implemented)
python tools/from-screenshot.py hero.png --output page.json

# Figma integration (not yet implemented)
python tools/from-figma.py "https://figma.com/..." --output page.json
```

**Workflow:**
1. Upload screenshot/Figma link
2. Claude Vision analyzes visual structure
3. Generates page description (structure, layout, colors)
4. Converts description to Elementor JSON (reuses Stage 2)

---

## Workflow: Fastest Path

### Option A: HTML You Have
```bash
# Webly export / website screenshot-to-HTML / Figma export
wget example.webly.com > page.html

# Convert
python tools/convert-html.py page.html

# Validate
python tools/validate-page.py page.json --target free

# Upload
wp eval-file tools/apply-page.php 123 page.json
```

**Time:** ~30 seconds + CSS tuning

### Option B: Just Describe It
```bash
# Natural language (no HTML needed)
python tools/from-description.py "hero + 3 cards + form" --output page.json

# Validate + upload (same as above)
python tools/validate-page.py page.json
wp eval-file tools/apply-page.php 123 page.json
```

**Time:** ~10 seconds

### Option C: Vibe Coding (Screenshot → Elementor)
```bash
# Screenshot → description (Claude Vision)
python tools/from-screenshot.py my-design.png --output page.json

# Upload
wp eval-file tools/apply-page.php 123 page.json
```

**Time:** ~20 seconds (requires API key)

---

## CSS & JavaScript Handling

### CSS
1. **Extracted to `out.css`** — inline styles from HTML
2. **Add to Elementor** → Page Settings → Custom CSS
3. **Or keep inline** → Use Elementor's color/spacing controls

Typical additions:
```css
/* Gradients */
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);

/* Hover effects */
.elementor-widget-heading:hover { transform: scale(1.05); }

/* Animations */
@keyframes fadeInUp { ... }
```

### JavaScript
1. **Detected** → listed in hints.md
2. **Add manually** → Elementor custom code block
3. **Or use Motion FX** → built-in animations don't need code

Common JS features:
```javascript
// Smooth scroll
document.querySelectorAll('a[href^="#"]').forEach(link => {
  link.addEventListener('click', (e) => {
    e.preventDefault();
    const target = document.querySelector(link.getAttribute('href'));
    target.scrollIntoView({ behavior: 'smooth' });
  });
});

// Hover animations
document.querySelectorAll('.card').forEach(card => {
  card.addEventListener('mouseenter', () => {
    card.style.transform = 'translateY(-5px)';
  });
  card.addEventListener('mouseleave', () => {
    card.style.transform = 'translateY(0)';
  });
});
```

---

## Limitations & Next Steps

| Feature | Status | Notes |
|---|---|---|
| HTML → Elementor | ✅ Done | Handles basic layouts, multi-column grids |
| Natural language → Elementor | ✅ Done | Claude Opus generates structure |
| Screenshot → Elementor | 🔲 TODO | Needs Claude Vision integration |
| Figma → Elementor | 🔲 TODO | Figma API + design tokenization |
| Advanced animations | 🟡 Partial | Detected, you add code |
| Dynamic content (WooCommerce) | ⚠️ Limited | Can place widgets, not bind data |
| Theme builder templates | 🔲 TODO | Requires condition system |

---

## API Usage & Costs

### convert-html.py
- **No API needed** — local Python only
- **Cost:** $0
- **Speed:** <1 second

### from-description.py
- **Needs:** Anthropic API key
- **Model:** Claude Opus 4.1 (best reasoning)
- **Cost:** ~$0.01-0.05 per page (input tokens only, no vision)
- **Speed:** ~3-5 seconds

### from-screenshot.py (future)
- **Needs:** Anthropic API key + image upload
- **Model:** Claude Opus 4.1 with Vision
- **Cost:** ~$0.10-0.20 per screenshot (includes image processing)
- **Speed:** ~5-10 seconds

---

## Examples & Testing

```bash
# Test HTML conversion
python tools/convert-html.py examples/test-page.html

# Test natural language (requires API key)
export ANTHROPIC_API_KEY="sk-..."
python tools/from-description.py "Hero + testimonials + footer"

# Validate result
python tools/validate-page.py page.json --target free

# Upload to WordPress
wp eval-file tools/apply-page.php 123 page.json
```

---

## Integrating with Your Workflow

### For Design → Code Teams
```
Designer makes Figma design
  ↓
from-screenshot.py (Stage 3)
  ↓
Developer reviews page.json + CSS
  ↓
Uploads to WordPress
  ↓
Designer fine-tunes in Elementor (if needed)
```

### For No-Code Creators
```
Describe page idea
  ↓
from-description.py
  ↓
Validate + upload
  ↓
Done (or customize in Elementor)
```

### For Porting Existing Sites
```
Export site HTML (or screenshot)
  ↓
convert-html.py
  ↓
Validate + fix CSS
  ↓
Upload
```
