# 🎨 God Eye Dashboard — Design & UI/UX Guidelines

> Panduan lengkap styling, UI/UX, dan design patterns untuk God Eye Dashboard.
> **Fokus:** visual appearance, user interaction, design consistency.  
> **Abaikan:** config, API, backend logic.

---

## 📑 Daftar Isi

1. [Design Philosophy](#design-philosophy)
2. [Color Palette](#color-palette)
3. [Typography](#typography)
4. [Components](#components)
5. [Layouts & Spacing](#layouts--spacing)
6. [Animations & Transitions](#animations--transitions)
7. [Dark Mode](#dark-mode)
8. [Responsive Design](#responsive-design)
9. [Interactive Elements](#interactive-elements)
10. [Page-Specific Designs](#page-specific-designs)

---

## Design Philosophy

### Core Aesthetic
- **Glassmorphism** — frosted glass effect dengan backdrop blur dan semi-transparent backgrounds
- **Cyberpunk/Futuristic** — neon accents, grid patterns, glowing shadows
- **Dark-first** — semua desain dimulai dari dark mode (tidak light mode)
- **High contrast** — mudah dibaca di semua kondisi cahaya
- **Smooth micro-interactions** — tidak ada jarring transitions, semua smooth 0.3-0.5s

### Design Tokens

| Aspect | Value |
|--------|-------|
| Base Color | `#0f0f1a` (surface.DEFAULT) |
| Grid Size | 4px (Tailwind spacing unit) |
| Border Radius | Small: 8px (`rounded-lg`), Medium: 12px (`rounded-xl`), Large: 16px (`rounded-2xl`) |
| Transition Duration | Fast: 150ms, Normal: 300ms, Slow: 500ms |
| Animation Easing | `cubic-bezier(0.4, 0, 0.6, 1)` (ease-in-out smooth) |

---

## Color Palette

### Primary Colors

```css
/* Brand — Indigo */
brand-50:  #eef2ff
brand-100: #e0e7ff
brand-200: #c7d2fe
brand-300: #a5b4fc
brand-400: #818cf8
brand-500: #6366f1 (PRIMARY)
brand-600: #4f46e5
brand-700: #4338ca
brand-800: #3730a3
brand-900: #312e81
```

**Usage:** Primary buttons, navigation, accent highlights, focus states

### Surface — Dark Theme

```css
surface.DEFAULT: #0f0f1a (Base background — body, main page)
surface.1:       #13131f (Subtle elevation — cards, containers)
surface.2:       #1a1a2e (Medium elevation — glass panels)
surface.3:       #1e1e35 (Higher elevation — modals, overlays)
surface.4:       #252540 (Highest elevation — dropdowns, tooltips)
```

**Usage Hierarchy:**
- `surface.DEFAULT` — page background
- `surface.1` — light cards, subtle containers
- `surface.2` — main glass panels (glassmorphism effect)
- `surface.3` — modals, sidebars, persistent overlays
- `surface.4` — transient UI (dropdowns, popovers)

### Accent Colors

| Color | Hex | Usage |
|-------|-----|-------|
| **Cyan** | `#06b6d4` | Secondary highlights, "survey" status, optional accents |
| **Violet** | `#8b5cf6` | Tertiary accents, special badges, premium indicators |
| **Green** | `#10b981` | Positive status, high scores (80+), success messages |
| **Amber** | `#f59e0b` | Medium scores (60-79), warnings, "in progress" |
| **Rose** | `#f43f5e` | Negative status, low scores (<60), delete action, high fraud risk |

### Neutral Palette

| Color | Hex | Usage |
|-------|-----|-------|
| **Slate-100** | `#f1f5f9` | Text headers (on dark) |
| **Slate-200** | `#e2e8f0` | Primary text on dark |
| **Slate-400** | `#94a3b8` | Secondary text, muted labels |
| **Slate-500** | `#64748b` | Tertiary text, metadata, timestamps |
| **Slate-600** | `#475569` | Disabled text, very subtle elements |

---

## Typography

### Font Stack

```css
font-family: {
  sans: 'Inter, sans-serif',        /* Default body text, UI labels, buttons */
  mono: 'JetBrains Mono, monospace' /* Code, IDs, prices, technical values */
}
```

### Sizes & Hierarchy

| Use | Size | Weight | Letter-spacing |
|-----|------|--------|-----------------|
| **Hero Title** | 32px/2rem | Bold 700 | -0.02em |
| **Page Title** | 24px/1.5rem | Bold 700 | -0.01em |
| **Section Title** | 20px/1.25rem | Bold 700 | 0 |
| **Card Title** | 18px/1.125rem | Semibold 600 | 0 |
| **Body Large** | 16px/1rem | Regular 400 | 0 |
| **Body Normal** | 14px/0.875rem | Regular 400 | 0 |
| **Label** | 12px/0.75rem | Medium 500 | 0.05em (uppercase) |
| **Small Text** | 11px/0.6875rem | Regular 400 | 0 |
| **Technical** | 13px/0.8125rem | Medium 500 (mono) | 0 |
| **Price** | 16-24px | Bold 700 (mono) | 0 |
| **Badge** | 12px/0.75rem | Semibold 600 | 0.05em |

### Examples

```html
<!-- Hero Title -->
<h1 class="text-2xl font-bold">God Eye Dashboard</h1>

<!-- Section Title -->
<h2 class="text-xl font-bold mb-4">Filter & Pencarian</h2>

<!-- Body Text -->
<p class="text-sm text-slate-200">Rata-rata Score</p>

<!-- Technical Value (mono) -->
<p class="font-mono text-sm font-semibold text-slate-300">1.2 km</p>

<!-- Price -->
<p class="font-mono text-lg font-bold">Rp 500.000</p>

<!-- Badge -->
<span class="text-xs font-semibold uppercase tracking-wider">Total</span>
```

---

## Components

### 1. Stat Cards (Hero Stats at Top)

**Location:** Index page top section  
**Layout:** 3-column grid (responsive: 1 col mobile, 2 col tablet, 3 col desktop)  
**Component Count:** 3 (Total, Avg Score, Surveyed)

#### Structure
```html
<div class="glass rounded-2xl p-5 glass-hover">
  <!-- Background gradient orb (top-right) -->
  <div class="absolute top-0 right-0 w-24 h-24 rounded-full blur-2xl opacity-20 pointer-events-none"
       style="background: radial-gradient(circle, #6366f1, transparent); transform: translate(30%, -30%);"></div>
  
  <!-- Header: icon + label -->
  <div class="flex items-start justify-between mb-3">
    <div class="w-10 h-10 rounded-xl flex items-center justify-center"
         style="background: rgba(99,102,241,0.15); border: 1px solid rgba(99,102,241,0.3);">
      <svg class="w-5 h-5 text-brand-400"><!-- icon --></svg>
    </div>
    <span class="text-xs font-mono text-slate-500 uppercase tracking-wider">Label</span>
  </div>
  
  <!-- Value + Description -->
  <p class="text-4xl font-bold gradient-text font-mono">VALUE</p>
  <p class="text-slate-400 text-sm mt-1 font-medium">Description</p>
</div>
```

#### Styling Details
- **Glass effect:** `background: rgba(255,255,255,0.05); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1);`
- **Icon box:** Colored bg (15% opacity) + border (30% opacity), icon color matches brand
- **Value text:** Large bold mono font, gradient effect
- **Hover state:** Subtle border brightening + slight background shift
- **Animation:** `slideUp 0.4s ease-out both` with staggered `animation-delay` (0s, 0.1s, 0.2s)

#### Color Variants per Card
- **Total (Brand):** Indigo gradient orb, indigo icon bg/border
- **Avg Score (Green):** Green gradient orb, green icon bg/border  
- **Surveyed (Cyan):** Cyan gradient orb, cyan icon bg/border

---

### 2. Filter Panel

**Location:** Below stat cards  
**Layout:** 6-column grid (responsive)  
**Contents:** Min price, Max price, Min distance, Max distance, Search, Sort dropdown

#### Structure
```html
<div class="glass rounded-2xl p-5 mb-6" id="filter-panel">
  <!-- Header -->
  <div class="flex items-center gap-2 mb-4">
    <div class="w-6 h-6 rounded-lg flex items-center justify-center"
         style="background: rgba(99,102,241,0.2); border:1px solid rgba(99,102,241,0.3);">
      <svg class="w-3.5 h-3.5 text-brand-400"><!-- filter icon --></svg>
    </div>
    <h2 class="text-sm font-semibold text-slate-200">Filter &amp; Pencarian</h2>
  </div>

  <!-- Form Grid -->
  <form id="filter-form" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
    <!-- Input fields -->
    <input type="number" class="input-field" placeholder="Min Harga..." />
    <!-- ... more inputs ... -->
  </form>
</div>
```

#### Input Styling

```css
.input-field {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 0.75rem;
  padding: 0.625rem 0.75rem;
  font-size: 0.875rem;
  color: #e2e8f0;
  transition: all 0.3s ease;
}

.input-field::placeholder {
  color: #64748b;
}

.input-field:focus {
  outline: none;
  background: rgba(255,255,255,0.08);
  border-color: rgba(99,102,241,0.5);
  box-shadow: 0 0 12px rgba(99,102,241,0.2);
}

.input-field:hover {
  border-color: rgba(99,102,241,0.3);
}
```

#### Label Styling
```html
<label class="text-xs text-slate-500 font-mono uppercase tracking-wider">Label Text</label>
```

---

### 3. Listing Cards (Grid)

**Location:** Main content area below filter  
**Layout:** Responsive grid (1 col mobile, 2 col tablet, 3-4 col desktop)  
**Interaction:** Hover reveals delete button, click navigates to detail

#### Card Structure
```html
<div class="group relative rounded-2xl overflow-hidden glass glass-hover transition-all duration-300
            hover:shadow-glow-brand cursor-pointer"
     onclick="navigateToListing(id)">
  
  <!-- Background image (optional) -->
  <div class="absolute inset-0 bg-gradient-to-br from-brand-500/20 to-transparent opacity-0 
              group-hover:opacity-100 transition-opacity duration-300"></div>
  
  <!-- Content -->
  <div class="relative p-4">
    
    <!-- Header: location + source badge -->
    <div class="flex items-start justify-between mb-2">
      <h3 class="text-sm font-semibold text-slate-100">Location Name</h3>
      <span class="badge badge-pending text-xs">source</span>
    </div>
    
    <!-- Price & Jarak row -->
    <div class="flex items-center gap-3 mb-3">
      <div class="flex items-center gap-1 text-xs">
        <svg class="w-3.5 h-3.5 text-green-400"><!-- money icon --></svg>
        <span class="font-mono font-semibold">Rp 500k</span>
      </div>
      <div class="flex items-center gap-1 text-xs">
        <svg class="w-3.5 h-3.5 text-cyan-400"><!-- location icon --></svg>
        <span class="font-mono font-semibold">1.2 km</span>
      </div>
    </div>
    
    <!-- Score + Status row -->
    <div class="flex items-center justify-between mb-2">
      <span class="font-mono text-xs font-bold
        {% if score >= 80 %}score-high{% elif score >= 60 %}score-mid{% else %}score-low{% endif %}">
        {{ score }}/100
      </span>
      <span class="badge
        {% if status == 'survey' %}badge-survey
        {% elif status == 'skip' %}badge-skip
        {% else %}badge-pending{% endif %} text-xs">
        {{ status_label }}
      </span>
    </div>
    
    <!-- Description (1-2 lines, truncate) -->
    <p class="text-xs text-slate-500 line-clamp-2 mb-3">{{ description }}</p>
    
    <!-- Footer: phones + delete button -->
    <div class="flex items-center justify-between">
      <span class="badge badge-secondary text-xs">📞 {{ phones_count }}</span>
      <button onclick="event.stopPropagation(); confirmDelete(id)"
              class="opacity-0 group-hover:opacity-100 transition-opacity duration-200
                     flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-semibold
                     text-rose-400 border hover:bg-rose-500/10"
              style="border-color: rgba(244,63,94,0.3);">
        <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
        </svg>
        <span class="hidden sm:inline">Hapus</span>
      </button>
    </div>
  </div>
</div>
```

#### Card Styling
- **Base:** `glass` class (glassmorphism effect), `rounded-2xl`
- **Padding:** `p-4` (16px on all sides)
- **Hover state:** Glow shadow (`shadow-glow-brand`), slight scale-up (transform: scale(1.02))
- **Delete button:** Hidden by default, visible on hover with `group-hover:opacity-100`
- **Transitions:** All smooth 200-300ms

#### Badge Types
```css
.badge {
  display: inline-flex;
  align-items: center;
  padding: 0.25rem 0.75rem;
  border-radius: 0.5rem;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.badge-pending {
  background: rgba(99,102,241,0.15);
  color: #818cf8;
  border: 1px solid rgba(99,102,241,0.25);
}

.badge-survey {
  background: rgba(16,185,129,0.15);
  color: #10b981;
  border: 1px solid rgba(16,185,129,0.25);
}

.badge-skip {
  background: rgba(244,63,94,0.15);
  color: #f43f5e;
  border: 1px solid rgba(244,63,94,0.25);
}
```

---

### 4. Detail Page — Hero Section

**Location:** Top of detail page  
**Layout:** Flex row (responsive: column on mobile, row on desktop)  
**Contains:** Score ring, title/info, buttons (View Source, Delete)

#### Structure
```html
<div class="glass rounded-2xl p-6 mb-5 flex flex-col sm:flex-row items-start sm:items-center gap-6">
  
  <!-- Score Ring -->
  <div class="relative flex-shrink-0 w-28 h-28 mx-auto sm:mx-0" id="score-ring-wrap">
    <svg class="w-28 h-28" viewBox="0 0 100 100">
      <circle cx="50" cy="50" r="42" fill="none" stroke="rgba(255,255,255,0.05)" stroke-width="8"/>
      <circle cx="50" cy="50" r="42" fill="none" 
              stroke="{% if score >= 80 %}#10b981{% elif score >= 60 %}#f59e0b{% else %}#f43f5e{% endif %}"
              stroke-width="8"
              stroke-linecap="round"
              stroke-dasharray="0 263.9"
              id="score-arc"
              data-score="{{ score }}"
              class="score-ring"/>
    </svg>
    <div class="absolute inset-0 flex flex-col items-center justify-center">
      <span class="text-2xl font-bold font-mono {% if score >= 80 %}score-high{% elif score >= 60 %}score-mid{% else %}score-low{% endif %}">
        {{ score }}
      </span>
      <span class="text-xs text-slate-500 font-mono">/100</span>
    </div>
  </div>
  
  <!-- Identity -->
  <div class="flex-1 min-w-0">
    <h1 class="text-xl font-bold text-slate-100 mb-2">{{ location }}</h1>
    
    <!-- Badges row -->
    <div class="flex flex-wrap items-center gap-2 mb-3">
      <span class="badge {% if fraud_risk == 'HIGH' %}fraud-high{% elif fraud_risk == 'MEDIUM' %}fraud-medium{% else %}fraud-low{% endif %}">
        {{ fraud_label }}
      </span>
      <span class="badge {% if status == 'survey' %}badge-survey{% elif status == 'skip' %}badge-skip{% else %}badge-pending{% endif %}">
        {{ status_label }}
      </span>
    </div>
    
    <!-- Metadata -->
    <p class="text-xs font-mono text-slate-600">
      ID: <code class="text-slate-500 bg-white/5 px-2 py-0.5 rounded">{{ id }}</code>
      &nbsp;·&nbsp; {{ timestamp }}
    </p>
  </div>
  
  <!-- Buttons -->
  <button onclick="showDeleteModal()" class="btn-delete flex items-center gap-2">
    <svg><!-- trash icon --></svg>
    Hapus
  </button>
</div>
```

#### Score Ring Animation
```css
.score-ring {
  transition: stroke-dasharray 0.8s ease-out, filter 0.6s ease-out;
  filter: drop-shadow(0 0 8px {% if score >= 80 %}rgba(16,185,129,0.7){% elif score >= 60 %}rgba(245,158,11,0.7){% else %}rgba(244,63,94,0.7){% endif %});
}
```

---

### 5. Info Cards Grid (Detail Page)

**Location:** Below hero in detail page  
**Layout:** 5-column grid (responsive to fewer columns on smaller screens)  
**Cards:** Price, Jarak, AQI, Rooms, Updated

#### Single Info Card
```html
<div class="glass rounded-xl p-4 glass-hover">
  <!-- Icon + Label -->
  <div class="flex items-center gap-2 mb-2">
    <div class="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
         style="background:rgba(16,185,129,0.15);border:1px solid rgba(16,185,129,0.25)">
      <svg class="w-3.5 h-3.5" style="color:#10b981"><!-- icon --></svg>
    </div>
    <span class="text-xs text-slate-500 font-mono uppercase">Label</span>
  </div>
  
  <!-- Value -->
  <p class="font-bold text-slate-200 text-sm">Value</p>
  
  <!-- Subtext -->
  <p class="text-xs text-slate-600 mt-0.5">Subtext</p>
</div>
```

#### Color-coded Info Cards
- **Price (Green):** Green icon, green accents
- **Distance (Cyan):** Cyan icon, cyan accents
- **AQI (Color per severity):** Varied color based on value
- **Rooms (Violet):** Violet icon
- **Updated (Slate):** Gray/slate accents

---

### 6. Delete Modal/Confirm

**Trigger:** Click delete button anywhere  
**Behavior:** Overlay dark, centered modal with fade-in animation

#### Modal Structure
```html
<div id="delete-modal" class="hidden fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50"
     onclick="if(event.target.id==='delete-modal') cancelDelete()">
  
  <div class="glass rounded-2xl p-6 max-w-sm w-full mx-4"
       style="animation: slideUp 0.3s ease-out both;">
    
    <!-- Icon + Title -->
    <div class="flex items-start gap-3 mb-4">
      <div class="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
           style="background:rgba(244,63,94,0.15);border:1px solid rgba(244,63,94,0.3)">
        <svg class="w-6 h-6 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4v.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
        </svg>
      </div>
      <div>
        <h3 class="text-lg font-bold text-slate-100">Hapus Listing?</h3>
        <p class="text-sm text-slate-400 mt-0.5">Aksi ini tidak bisa dibatalkan.</p>
      </div>
    </div>
    
    <!-- Listing preview -->
    <div class="bg-white/5 rounded-lg p-3 mb-4">
      <p class="text-xs text-slate-500 font-mono mb-1">ID: {{ id }}</p>
      <p class="text-sm font-semibold text-slate-200">{{ location }}</p>
    </div>
    
    <!-- Button group -->
    <div class="flex gap-2">
      <button onclick="cancelDelete()"
              class="flex-1 px-4 py-2 rounded-lg text-sm font-semibold
                     text-slate-300 bg-white/5 hover:bg-white/10
                     transition-colors duration-200">
        Batal
      </button>
      <button onclick="doDelete()"
              class="flex-1 px-4 py-2 rounded-lg text-sm font-semibold
                     text-white bg-rose-600 hover:bg-rose-500
                     transition-colors duration-200">
        Hapus Selamanya
      </button>
    </div>
  </div>
</div>
```

#### Modal Styling
- **Overlay:** `bg-black/40 backdrop-blur-sm` (semi-transparent dark with blur)
- **Modal box:** Glass effect, centered with `flex items-center justify-center`
- **Animation:** `slideUp 0.3s ease-out both` (pop in from bottom)
- **Close trigger:** Click outside modal (overlay click) or "Batal" button

---

### 7. Toast Notifications

**Trigger:** After delete success, copy ID, or other actions  
**Position:** Bottom-right corner  
**Duration:** Auto-dismiss after 3-4 seconds

#### Structure
```html
<div id="toast" class="hidden fixed bottom-4 right-4 glass rounded-xl px-4 py-3 flex items-center gap-3 z-50"
     style="animation: slideUp 0.3s ease-out both;">
  <div class="w-5 h-5 flex-shrink-0">
    <svg class="w-5 h-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
      <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
    </svg>
  </div>
  <span class="text-sm font-medium text-slate-100">Listing berhasil dihapus</span>
</div>
```

#### Toast Styling
- **Position:** `fixed bottom-4 right-4` (bottom-right)
- **Animation:** `slideUp 0.3s ease-out both` then fade-out after 3s
- **Icon color:** Green for success, amber for warning, rose for error
- **Background:** Glass effect with rounded corners

---

### 8. Back Navigation Button

**Location:** Top-left of detail page  
**Behavior:** Navigate back to dashboard with smooth transition

#### Structure
```html
<a href="/dashboard"
   class="inline-flex items-center gap-2 text-slate-400 hover:text-slate-200 text-sm transition-colors group"
   onclick="if(typeof SFX!=='undefined')SFX.nav()">
  <svg class="w-4 h-4 transition-transform group-hover:-translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
    <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"/>
  </svg>
  Kembali ke Dashboard
</a>
```

#### Styling
- **Text color:** Muted slate-400, brightens to slate-200 on hover
- **Icon animation:** Slight left translate on hover (`group-hover:-translate-x-1`)
- **Transition:** Smooth 200ms

---

## Layouts & Spacing

### Page Structure

```
┌─────────────────────────────────────┐
│  Header / Navbar                    │  (height: auto, padding: 1rem)
├─────────────────────────────────────┤
│                                     │
│  Main content (max-width: 1400px)   │  (padding: 2rem on sides, 1.5rem top/bottom)
│  margin: 0 auto                     │
│                                     │
└─────────────────────────────────────┘
```

### Spacing Scale

| Value | Usage |
|-------|-------|
| `gap-1` (4px) | Tiny spacing between icon + text |
| `gap-2` (8px) | Small spacing in badges, tight layouts |
| `gap-3` (12px) | Normal spacing between elements |
| `gap-4` (16px) | Medium spacing between sections |
| `gap-6` (24px) | Large spacing between major blocks |

### Padding Scale

| Value | Usage |
|-------|-------|
| `p-3` (12px) | Small cards, compact elements |
| `p-4` (16px) | Standard card padding |
| `p-5` (20px) | Stat cards, larger containers |
| `p-6` (24px) | Hero sections, prominent cards |

### Responsive Breakpoints (Tailwind)

| Breakpoint | Screen Size | Usage |
|-----------|-------------|-------|
| `sm:` | 640px | Tablets |
| `md:` | 768px | Small desktops |
| `lg:` | 1024px | Desktops |
| `xl:` | 1280px | Large desktops |
| `2xl:` | 1536px | Extra large |

### Container Queries

```css
max-width: 1400px;
margin-left: auto;
margin-right: auto;
```

---

## Animations & Transitions

### Global Transition Defaults

```css
transition-duration: 300ms;
transition-timing-function: cubic-bezier(0.4, 0, 0.6, 1); /* ease-in-out */
```

### Keyframe Animations

#### slideUp
```css
@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
/* Duration: 0.4-0.5s ease-out */
```

#### fadeIn
```css
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
/* Duration: 0.3s ease-out */
```

#### float
```css
@keyframes float {
  0%, 100% { transform: translateY(0px); }
  50% { transform: translateY(-10px); }
}
/* Duration: 6s ease-in-out infinite (background orbs) */
```

#### shimmer
```css
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
/* Duration: 2s linear infinite (loading skeleton) */
```

### Micro-interactions

#### Hover States

```css
/* Buttons */
button {
  transition: all 0.2s ease;
}
button:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 16px rgba(99,102,241,0.3);
}
button:active {
  transform: translateY(0);
}

/* Cards */
.glass:hover {
  border-color: rgba(99,102,241,0.4);
  background: rgba(255,255,255,0.08);
}

/* Links */
a:hover {
  color: #e2e8f0; /* brighten text */
}
a svg {
  transition: transform 0.2s ease;
}
a:hover svg {
  transform: translateX(-2px); /* slight movement */
}
```

#### Focus States
```css
input:focus {
  outline: none;
  box-shadow: 0 0 12px rgba(99,102,241,0.3);
  border-color: rgba(99,102,241,0.5);
}

button:focus-visible {
  outline: 2px solid rgba(99,102,241,0.6);
  outline-offset: 2px;
}
```

### Staggered Animation (multiple elements)

```html
<div style="animation: slideUp 0.4s ease-out both; animation-delay: 0.0s;"><!-- 1st --></div>
<div style="animation: slideUp 0.4s ease-out both; animation-delay: 0.1s;"><!-- 2nd --></div>
<div style="animation: slideUp 0.4s ease-out both; animation-delay: 0.2s;"><!-- 3rd --></div>
```

---

## Dark Mode

### Strategy
- **Always dark** — no light mode toggle needed currently
- HTML root: `<html lang="id" class="dark">` — forces Tailwind dark mode
- All colors designed for dark backgrounds

### Dark Mode Color Scheme

```
Background:   #0f0f1a (surface.DEFAULT)
Surface 1:    #13131f (subtle elevation)
Surface 2:    #1a1a2e (medium elevation)
Text Primary: #e2e8f0 (slate-200)
Text Muted:   #94a3b8 (slate-400)
Accent:       #6366f1, #10b981, #06b6d4, #f59e0b, #f43f5e
```

### Text Legibility
- **Primary text** (slate-100, slate-200) — >7:1 contrast ratio ✅
- **Secondary text** (slate-400, slate-500) — >4.5:1 contrast ratio ✅
- **Disabled text** (slate-600) — >3:1 contrast ratio (acceptable for disabled)

---

## Responsive Design

### Mobile First (Tailwind convention)

```css
/* Base styles — applies to all sizes */
.card { padding: 1rem; }

/* Tablet and up */
@media (min-width: 640px) {
  .card { padding: 1.25rem; }
}

/* Desktop and up */
@media (min-width: 1024px) {
  .card { padding: 1.5rem; }
}
```

### Breakpoint Usage Examples

```html
<!-- Responsive grid -->
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
  <!-- 1 col on mobile, 2 on tablet, 4 on desktop -->
</div>

<!-- Responsive text -->
<p class="text-sm sm:text-base lg:text-lg">
  Text size adapts per screen
</p>

<!-- Responsive layout -->
<div class="flex flex-col sm:flex-row gap-3 sm:gap-6">
  <!-- Column on mobile, row on tablet+ -->
</div>

<!-- Hide/Show based on breakpoint -->
<span class="hidden sm:inline">Show on tablet+</span>
<span class="sm:hidden">Show on mobile only</span>
```

### Grid Responsiveness

| Component | Mobile | Tablet | Desktop |
|-----------|--------|--------|---------|
| **Stat Cards** | 1 col | 2 col | 3 col |
| **Listing Cards** | 1 col | 2 col | 3-4 col |
| **Filter Inputs** | 2 col | 3 col | 6 col |
| **Info Cards** | 2 col | 3 col | 5 col |

---

## Interactive Elements

### Buttons

#### Primary Button (CTA)
```css
.btn-primary {
  background: #6366f1; /* brand-500 */
  color: #ffffff;
  border: none;
  border-radius: 0.75rem;
  padding: 0.625rem 1rem;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}

.btn-primary:hover {
  background: #4f46e5; /* brand-600 */
  box-shadow: 0 0 16px rgba(99,102,241,0.4);
  transform: translateY(-2px);
}

.btn-primary:active {
  transform: translateY(0);
}
```

#### Secondary Button
```css
.btn-secondary {
  background: rgba(255,255,255,0.05);
  color: #cbd5e1;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 0.75rem;
  padding: 0.625rem 1rem;
  transition: all 0.3s ease;
}

.btn-secondary:hover {
  background: rgba(255,255,255,0.1);
  border-color: rgba(255,255,255,0.15);
}
```

#### Danger Button (Delete)
```css
.btn-delete {
  background: rgba(244,63,94,0.08);
  color: #f43f5e;
  border: 1px solid rgba(244,63,94,0.25);
  border-radius: 0.75rem;
  padding: 0.625rem 1rem;
  font-weight: 600;
  transition: all 0.3s ease;
}

.btn-delete:hover {
  background: rgba(244,63,94,0.18);
  border-color: rgba(244,63,94,0.4);
}
```

### Form Inputs

```css
input, select, textarea {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 0.625rem;
  color: #e2e8f0;
  padding: 0.625rem 0.75rem;
  font-size: 0.875rem;
  transition: all 0.3s ease;
}

input::placeholder {
  color: #64748b;
}

input:focus, select:focus, textarea:focus {
  outline: none;
  background: rgba(255,255,255,0.08);
  border-color: rgba(99,102,241,0.5);
  box-shadow: 0 0 12px rgba(99,102,241,0.2);
}

input:hover, select:hover, textarea:hover {
  border-color: rgba(99,102,241,0.3);
}
```

---

## Page-Specific Designs

### Index Page (Dashboard / Listings)

**Flow:**
1. Stat cards (3 cards in grid) — animated slideUp
2. Filter panel (input fields in grid)
3. Listing cards grid (responsive)

**Vertical rhythm:**
- Stat cards → 24px gap → Filter panel → 24px gap → Listing grid
- Within listing grid: 12px gap

### Detail Page

**Flow:**
1. Back navigation link
2. Hero section (score + info + buttons)
3. Info cards grid (5 columns)
4. Sections (phones, maps, AI analysis)

**Vertical rhythm:**
- Back link → 20px → Hero → 20px → Info cards → 20px → Sections

### Navigation Bar (Future)

**Expected:**
- Logo/brand on left
- Search bar (optional)
- Sound toggle button 🔊
- Settings/menu on right

---

## Glassmorphism Effect

### Core CSS
```css
.glass {
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 1rem;
}

.glass:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.15);
}

/* Stronger glass (modals, overlays) */
.glass-strong {
  background: rgba(20, 20, 35, 0.8);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.15);
}
```

### Color Glow Effects
```css
.glow-brand {
  box-shadow: 0 0 20px rgba(99, 102, 241, 0.35);
}

.glow-cyan {
  box-shadow: 0 0 20px rgba(6, 182, 212, 0.35);
}

.glow-green {
  box-shadow: 0 0 20px rgba(16, 185, 129, 0.25);
}
```

---

## Accessibility Considerations

### Color Contrast
- ✅ All text meets WCAG AA standards (4.5:1 minimum)
- ✅ Color not sole method of information conveyance (badges have text + icons)
- ✅ Focus states clearly visible

### Keyboard Navigation
- ✅ All buttons/links focusable via Tab
- ✅ Focus indicators visible (blue glow or outline)
- ✅ Enter/Space triggers buttons

### Screen Readers
- ✅ Semantic HTML (`<button>`, `<label>`, `<a>`)
- ✅ SVG icons have `aria-label` where needed
- ✅ Form inputs have associated `<label>` elements

### Motion Sensitivity
- ⚠️ **Note:** Current animations may be too much for users with motion sensitivity
- **Future:** Add `prefers-reduced-motion` media query support

```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## Common Issues & Solutions

### Issue: Text appears blurry on glass backgrounds
**Solution:** Use `backdrop-filter: blur(10px)` NOT `blur()` filter on text. Blur should only apply to background.

### Issue: Hover states don't feel responsive
**Solution:** Use `transform: translateY(-2px)` + `box-shadow` increase for tactile feedback.

### Issue: Mobile layout too cramped
**Solution:** Check responsive breakpoints — may need to adjust grid columns. Use `gap-2` instead of `gap-3` on mobile.

### Issue: Colors too bright/saturated
**Solution:** Use opacity-reduced variants (`opacity-50`, `opacity-30`) or move to lighter shade in palette.

### Issue: Animation jank on low-end devices
**Solution:** Reduce animation count, use simpler easing (avoid `cubic-bezier`), increase animation duration.

---

## Future Design Enhancements

- [ ] Light mode toggle (if needed)
- [ ] Custom theme picker (accent color, darkness level)
- [ ] Accessibility: `prefers-reduced-motion` support
- [ ] Advanced animations: page transitions, skeleton loaders
- [ ] Dark subvariants (darker for OLED screens)
- [ ] Print stylesheet (for exporting listing details)

---

*Last updated: 2026-03-21*
