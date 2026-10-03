# GATE DA Atlas: web app

The browser front end of this repository. It maps every GATE DA question from 2024 to 2026 onto the
official syllabus. You can practise the questions against the official key, see trends and the
forecast, and run the adaptive study planner.

The data comes from the Python pipeline in the repository root and is not stored here. Generate it
first:

```bash
# from the repository root, with the Python environment active
python -m gate_atlas export-web    # writes src/data/*.json, public/crops/ and src/planner/fixtures/plans.json
```

Then, in this folder (Node.js 20.19+ or 22.12+):

```bash
npm install
npm run dev      # local preview
npm test         # the TypeScript planner must reproduce the Python plans exactly
npm run lint     # oxlint
npm run build    # type-check, then a static site in dist/ with relative paths
```

| Folder | Contents |
|---|---|
| `src/views/` | Map, Questions, Trends, Planner and Method views |
| `src/components/` | Syllabus map and tiles, item panel, practice box, SVG charts |
| `src/planner/` | TypeScript port of `gate_atlas.planner` and its parity tests |
| `src/styles/` | Design tokens for light and dark themes, and the layout |

The methodology is in the main [README](../README.md#methodology-phase-5).
