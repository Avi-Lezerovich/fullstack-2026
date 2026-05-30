# LolSuit — Database Schema

SQLite database (`database/lolsuit.db`), created from [`init.sql`](init.sql) and seeded from
[`server/app/models.py`](../server/app/models.py).

## Entity-Relationship Diagram

```mermaid
erDiagram
    users ||--o{ posts          : "writes"
    users ||--o| sessions       : "has active"
    posts ||--o{ post_charges   : "is charged with"
    users ||--o{ follows        : "follows (follower)"
    users ||--o{ follows        : "is followed (followee)"

    users {
        INTEGER id PK
        TEXT    name
        TEXT    email "UNIQUE"
        TEXT    password_hash "bcrypt"
        TEXT    bio "nullable"
        TEXT    avatar_url "nullable"
        TEXT    created_at "ISO-8601"
    }

    sessions {
        INTEGER user_id FK "UNIQUE — one active session/user"
        TEXT    session_id "opaque token"
        TEXT    created_at "ISO-8601"
    }

    posts {
        INTEGER id PK
        TEXT    title
        TEXT    body "sanitized rich-text HTML"
        TEXT    defendant
        TEXT    location "nullable"
        TEXT    image_url "nullable"
        INTEGER author_id FK
        TEXT    created_at "ISO-8601"
    }

    post_charges {
        INTEGER id PK
        INTEGER post_id FK
        TEXT    charge
    }

    follows {
        INTEGER follower_id FK "PK part"
        INTEGER followee_id FK "PK part"
        TEXT    created_at "ISO-8601"
    }
```

## Relationships

| From | To | Cardinality | Notes |
|---|---|---|---|
| `users` → `posts` | author | 1 — N | `posts.author_id` → `users.id`, `ON DELETE CASCADE` |
| `posts` → `post_charges` | charges | 1 — N | a post has zero or more charge labels |
| `users` → `sessions` | session | 1 — 1 | `sessions.user_id` is `UNIQUE`; a fresh login upserts the row |
| `users` ↔ `users` | follows | M — N | join table `follows(follower_id, followee_id)`; `CHECK (follower_id <> followee_id)` blocks self-follow |
