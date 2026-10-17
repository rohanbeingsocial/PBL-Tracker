"""Makes embeddings for projects that don't have one yet: newly loaded projects, and
projects whose title or abstract changed (a trigger clears the stale embedding).

    python -m scripts.embed_projects          only the missing ones
    python -m scripts.embed_projects --all    redo every project (after changing the model)
"""
import argparse

import psycopg

from finder.config import require
from finder.embeddings import MODEL_NAME, embed, project_text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="re-embed every project")
    args = parser.parse_args()

    with psycopg.connect(require("ADMIN_DATABASE_URL"), connect_timeout=10) as conn:
        rows = conn.execute(
            """SELECT project_id, title, abstract FROM pbl.projects
               WHERE %s OR embedding IS NULL
               ORDER BY project_id""",
            (args.all,),
        ).fetchall()
        if not rows:
            print("Every project already has an embedding.")
            return

        print(f"Embedding {len(rows)} projects with {MODEL_NAME} ...")
        vectors = embed([project_text(title, abstract) for _, title, abstract in rows])
        with conn.cursor() as cur:
            # The list of floats arrives as a float array and Postgres casts it to vector(384).
            cur.executemany(
                "UPDATE pbl.projects SET embedding = %s WHERE project_id = %s",
                [(vector, project_id) for (project_id, _, _), vector in zip(rows, vectors, strict=True)],
            )
    print("Done.")


if __name__ == "__main__":
    main()
