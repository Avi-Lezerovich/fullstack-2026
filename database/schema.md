# LolSuit — Database Schema

MySQL 8 database (`lolsuit`, e.g. on Amazon RDS), created from [`init.sql`](init.sql) and seeded
from [`server/app/models.py`](../server/app/models.py). All tables are InnoDB / `utf8mb4`.

## Entity-Relationship Diagram

```mermaid
erDiagram
    users ||--o{ posts          : "writes"
    users ||--o| sessions       : "has active"
    posts ||--o{ post_charges   : "is charged with"
    users ||--o{ follows        : "follows (follower)"
    users ||--o{ follows        : "is followed (followee)"

    users {
        INT          id PK
        VARCHAR      name
        VARCHAR      email "UNIQUE"
        VARCHAR      password_hash "bcrypt"
        TEXT         bio "nullable"
        VARCHAR      avatar_url "nullable"
        VARCHAR      created_at "ISO-8601"
    }

    sessions {
        INT          user_id FK "UNIQUE — one active session/user"
        VARCHAR      session_id "opaque token"
        VARCHAR      created_at "ISO-8601"
    }

    posts {
        INT          id PK
        VARCHAR      title
        TEXT         body "sanitized rich-text HTML"
        VARCHAR      defendant
        VARCHAR      image_url "nullable"
        INT          author_id FK
        VARCHAR      created_at "ISO-8601"
    }

    post_charges {
        INT          id PK
        INT          post_id FK
        VARCHAR      charge
    }

    follows {
        INT          follower_id FK "PK part"
        INT          followee_id FK "PK part"
        VARCHAR      created_at "ISO-8601"
    }
```

## Relationships

| From | To | Cardinality | Notes |
|---|---|---|---|
| `users` → `posts` | author | 1 — N | `posts.author_id` → `users.id`, `ON DELETE CASCADE` |
| `posts` → `post_charges` | charges | 1 — N | a post has zero or more charge labels |
| `users` → `sessions` | session | 1 — 1 | `sessions.user_id` is `UNIQUE`; a fresh login upserts the row |
| `users` ↔ `users` | follows | M — N | join table `follows(follower_id, followee_id)`; `CHECK (follower_id <> followee_id)` blocks self-follow |
