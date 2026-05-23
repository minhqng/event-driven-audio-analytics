# Decisions Register

<!-- Append-only. Never edit or remove existing rows.
     To reverse a decision, add a new row that supersedes it.
     Read this file at the start of any planning or research phase. -->

| # | When | Scope | Decision | Choice | Rationale | Revisable? | Made By |
|---|------|-------|----------|--------|-----------|------------|---------|
| D001 | M001 recovery and context tightening | architecture | Implementation architecture for the demo UI upgrade | Enhance the existing FastAPI-served static review console using HTML, CSS, and JavaScript, adding only small read-only API/status support where existing review data is insufficient. | The user selected the static UI path because the review console is already the demo front door, the project has no frontend build pipeline, and adding React/Vite would increase deployment and packaging complexity for a thesis demo. | Yes, but only if the static review console cannot meet the demo clarity or status requirements. | human |
