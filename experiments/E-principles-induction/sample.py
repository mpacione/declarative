"""Build a stratified 25-screen sample from the Dank corpus.

Stratification axes:
- Form factor: iphone / ipad_11 / ipad_13 (balanced ~8 each)
- Complexity: low / mid / high node count (split by tertile per form factor)
- Feature markers: at least one keyboard-containing screen, at least one with slider,
  multiple with checkbox lists, and a mix of chrome presence.

Output: sample.csv with columns screen_id, figma_node_id, name, device_class,
width, height, n_nodes, markers, tier.
"""

import csv
import random
import sqlite3
from collections import defaultdict
from pathlib import Path

DB = Path("/Users/mattpacione/declarative-build/Dank-EXP-02.declarative.db")
OUT_CSV = Path("/Users/mattpacione/declarative-build/experiments/E-principles-induction/sample.csv")
SAMPLE_SIZE = 25

def slugify(name: str) -> str:
    return (
        name.lower()
        .replace('"', "")
        .replace(" - ", "-")
        .replace(" ", "_")
        .replace("/", "_")
    )


def main() -> None:
    random.seed(11)
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          s.id, s.figma_node_id, s.name, s.device_class, s.width, s.height,
          (SELECT COUNT(*) FROM nodes n WHERE n.screen_id = s.id) AS n_nodes,
          EXISTS (
            SELECT 1 FROM nodes n JOIN component_key_registry c ON n.component_key = c.component_key
            WHERE n.screen_id = s.id AND (c.name LIKE '%\\_Key%' ESCAPE '\\')
          ) AS has_kbd,
          EXISTS (
            SELECT 1 FROM nodes n JOIN component_key_registry c ON n.component_key = c.component_key
            WHERE n.screen_id = s.id AND c.name = 'button/slider'
          ) AS has_slider,
          EXISTS (
            SELECT 1 FROM nodes n JOIN component_key_registry c ON n.component_key = c.component_key
            WHERE n.screen_id = s.id AND c.name IN ('icon/checkbox-empty', 'icon/checkbox-filled')
          ) AS has_chk,
          EXISTS (
            SELECT 1 FROM nodes n JOIN component_key_registry c ON n.component_key = c.component_key
            WHERE n.screen_id = s.id AND c.name = 'ios/status-bar'
          ) AS has_ios_chrome
        FROM screens s
        WHERE s.screen_type = 'app_screen'
        ORDER BY s.id
        """
    )
    rows = cur.fetchall()

    # Partition by form factor
    by_ff: dict[str, list[tuple]] = defaultdict(list)
    for r in rows:
        ff = r[3] if r[3] in ("iphone", "ipad_11", "ipad_13") else "iphone"
        by_ff[ff].append(r)

    # Quotas per form factor ~8 each
    quotas = {"iphone": 9, "ipad_11": 8, "ipad_13": 8}
    selected: list[tuple] = []

    for ff, quota in quotas.items():
        screens = by_ff[ff]
        screens_sorted = sorted(screens, key=lambda r: r[6])  # by n_nodes
        # tertile split
        n = len(screens_sorted)
        low = screens_sorted[: n // 3]
        mid = screens_sorted[n // 3 : 2 * n // 3]
        high = screens_sorted[2 * n // 3 :]

        # Guarantee distinctive features where possible
        chosen: list[tuple] = []
        # Pick one keyboard-containing screen (rare, ~5 total) if present in this ff
        kbd = [r for r in screens if r[7] == 1]
        if kbd:
            chosen.append(random.choice(kbd))
        # Pick one slider-containing screen if present
        sldr = [r for r in screens if r[8] == 1 and r not in chosen]
        if sldr:
            chosen.append(random.choice(sldr))
        # Fill remaining slots across tertiles with preference for balance
        remaining = quota - len(chosen)
        # Distribute across tertiles proportionally
        pick_low = remaining // 3
        pick_mid = remaining // 3
        pick_high = remaining - pick_low - pick_mid
        pools = [
            ([r for r in low if r not in chosen], pick_low),
            ([r for r in mid if r not in chosen], pick_mid),
            ([r for r in high if r not in chosen], pick_high),
        ]
        for pool, k in pools:
            if not pool or k <= 0:
                continue
            chosen.extend(random.sample(pool, min(k, len(pool))))

        # Dedup just in case
        seen_ids = set()
        deduped: list[tuple] = []
        for r in chosen:
            if r[0] in seen_ids:
                continue
            seen_ids.add(r[0])
            deduped.append(r)
        # If short, top up from any remaining in-ff pool
        if len(deduped) < quota:
            leftover = [r for r in screens if r[0] not in seen_ids]
            random.shuffle(leftover)
            deduped.extend(leftover[: quota - len(deduped)])

        selected.extend(deduped[:quota])

    # Write CSV
    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "screen_id",
                "figma_node_id",
                "name",
                "device_class",
                "width",
                "height",
                "n_nodes",
                "has_keyboard",
                "has_slider",
                "has_checkbox",
                "has_ios_chrome",
                "file_path",
                "slug",
            ]
        )
        for r in selected:
            sid, fnid, name, dev, w_, h_, nn, kb, sl, ck, ios = r
            slug = slugify(name)
            fpath = f"screenshots/{sid}-{slug}.png"
            w.writerow([sid, fnid, name, dev, w_, h_, nn, kb, sl, ck, ios, fpath, slug])

    print(f"wrote {OUT_CSV} with {len(selected)} rows")
    print("device_class distribution:")
    from collections import Counter
    print(Counter(r[3] for r in selected))


if __name__ == "__main__":
    main()
