"""Separate recipe library with immutable revisions and optimistic updates."""

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from app.recipes.models import RecipeDefinition, SavedRecipe, recipe_content_digest


class RecipeConflict(ValueError):
    pass


class RecipeStore:
    def __init__(self, path: Path):
        self.connection = sqlite3.connect(path)
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            tables = self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if not tables and version == 0:
                self.connection.execute("""
                    CREATE TABLE recipe_revisions (
                        recipe_id TEXT NOT NULL,
                        revision INTEGER NOT NULL CHECK(revision >= 1),
                        payload TEXT NOT NULL,
                        content_digest TEXT NOT NULL,
                        PRIMARY KEY(recipe_id, revision)
                    )
                """)
                self.connection.execute("PRAGMA user_version = 2")
            elif tables != [("recipe_revisions",)] or version != 2:
                raise RecipeConflict("unsupported recipe library schema")
            columns = self.connection.execute("PRAGMA table_info(recipe_revisions)").fetchall()
            if tuple((r[1], r[2], r[3], r[5]) for r in columns) != (
                ("recipe_id", "TEXT", 1, 1),
                ("revision", "INTEGER", 1, 2),
                ("payload", "TEXT", 1, 0),
                ("content_digest", "TEXT", 1, 0),
            ):
                raise RecipeConflict("unexpected recipe library structure")
            self.connection.commit()
        except BaseException:
            self.connection.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.connection.close()

    @staticmethod
    def _read(row):
        if row is None:
            return None
        recipe_id, revision, payload, content_digest = row

        # Preserve unknown-field/version rejection instead of guessing migrations.
        def unique_keys(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise RecipeConflict("duplicate keys in stored recipe")
                result[key] = value
            return result

        try:
            definition = RecipeDefinition.model_validate(
                json.loads(payload, object_pairs_hook=unique_keys)
            )
            return SavedRecipe(recipe_id=recipe_id, revision=revision, definition=definition,
                               content_digest=content_digest)
        except (ValidationError, json.JSONDecodeError) as exc:
            raise RecipeConflict("stored recipe content identity or schema mismatch") from exc

    def load(self, recipe_id):
        return self._read(
            self.connection.execute(
                "SELECT recipe_id, revision, payload, content_digest FROM recipe_revisions WHERE recipe_id=? ORDER BY revision DESC LIMIT 1",
                (recipe_id,),
            ).fetchone()
        )

    def list(self):
        rows = self.connection.execute("""SELECT r.recipe_id, r.revision, r.payload, r.content_digest
            FROM recipe_revisions r WHERE r.revision=(SELECT MAX(revision)
            FROM recipe_revisions WHERE recipe_id=r.recipe_id) ORDER BY r.recipe_id""").fetchall()
        return tuple(self._read(row) for row in rows)

    def save(self, definition, *, recipe_id=None, expected_revision=0):
        definition = RecipeDefinition.model_validate_json(definition.model_dump_json())
        recipe_id = recipe_id or str(uuid4())
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            current = self.load(recipe_id)
            revision = current.revision if current else 0
            if revision != expected_revision:
                raise RecipeConflict("recipe revision changed; reload before saving or running")
            revision += 1
            self.connection.execute(
                "INSERT INTO recipe_revisions VALUES (?, ?, ?, ?)",
                (recipe_id, revision, definition.model_dump_json(), recipe_content_digest(definition)),
            )
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise
        return SavedRecipe(recipe_id=recipe_id, revision=revision, definition=definition,
                           content_digest=recipe_content_digest(definition))
