/* Sequence-diagram steps, written by hand from the code. Rendered by guide.js. */
window.GUIDE_SEQ = {
    login: {
      actors: [["ui", "Login.tsx", "info"], ["ctx", "AuthContext", "info"], ["api", "api.ts", "info"], ["fl", "api/auth.py"], ["svc", "services"], ["db", "MySQL", "ok"]],
      steps: [
        ["ui", "ctx", "signIn(email, password)"],
        ["ctx", "api", "api.login()"],
        ["api", "fl", "POST /api/auth/login (credentials: include)"],
        ["fl", "svc", "users_service.get_by_email()"],
        ["svc", "db", "SELECT … FROM users WHERE email"],
        ["db", "svc", "row (password_hash, status)", 1],
        ["fl", "fl", "security.verify_password (bcrypt)"],
        ["fl", "svc", "auth_service.create_session()"],
        ["svc", "db", "INSERT sessions (token_hash = sha256)"],
        ["fl", "api", "200 {user} + Set-Cookie session_id; HttpOnly", 1],
        ["api", "ctx", "{ user }", 1],
        ["ctx", "ctx", "setUser(me)"]
      ]
    },
    file: {
      actors: [["ui", "NewCase.tsx", "info"], ["api", "api.ts", "info"], ["rt", "api/cases.py"], ["sec", "security.py"], ["svc", "cases_service"], ["mod", "moderation / sentiment", "gold"], ["db", "MySQL", "ok"]],
      steps: [
        ["ui", "api", "createCase(input)"],
        ["api", "rt", "POST /api/cases"],
        ["rt", "sec", "@require_auth → _load_user()"],
        ["sec", "db", "resolve_session (by token_hash)"],
        ["rt", "rt", "body_of · clean · title≥3 · body≥10"],
        ["rt", "svc", "create_case(author, title, body, …)"],
        ["svc", "mod", "screen(title + body) → sentiment.scan"],
        ["mod", "svc", "(\"published\" | \"flagged\" | \"rejected\", scan)", 1],
        ["svc", "db", "INSERT cases (status='witness_phase', deadline)"],
        ["svc", "db", "INSERT case_charges · record_scan"],
        ["svc", "db", "case_activity.touch · follows.follow(auto)"],
        ["svc", "db", "COMMIT"],
        ["svc", "rt", "(\"ok\", case_id)", 1],
        ["rt", "api", "201 {case}   (422 if rejected)", 1],
        ["api", "ui", "navigate(/cases/:id)", 1]
      ]
    },
    comment: {
      actors: [["a", "CommentComposer", "info"], ["api", "api.ts", "info"], ["rt", "api/social.py"], ["svc", "comments_service"], ["db", "MySQL", "ok"], ["st", "notifications.py stream"], ["b", "useNotificationStream (other user)", "info"]],
      steps: [
        { note: "earlier: new EventSource('/api/notifications/stream?since=N')", from: "st", to: "b" },
        ["a", "api", "createComment(caseId, body)"],
        ["api", "rt", "POST /api/cases/:id/comments"],
        ["rt", "svc", "create_comment(role='user')"],
        ["svc", "svc", "screen(body)"],
        ["svc", "db", "INSERT comments (depth, root_comment_id)"],
        ["svc", "db", "_notify_participants → INSERT notifications"],
        ["svc", "db", "case_activity.touch · COMMIT"],
        ["rt", "api", "201 {comment}", 1],
        ["st", "db", "every SSE_POLL_SECONDS: id > cursor ?"],
        ["db", "st", "new notification row", 1],
        ["st", "b", "event: notification   id: N+1", 1],
        ["b", "b", "NotificationContext → bell badge"]
      ]
    },
    trial: {
      actors: [["lp", "worker/loop.tick"], ["tt", "trial_tasks"], ["ts", "trial_service"], ["js", "jury_service"], ["br", "app/brain", "gold"], ["db", "MySQL", "ok"]],
      steps: [
        { note: "day 2 — witness phase ends", from: "lp", to: "db" },
        ["lp", "tt", "advance_witness_phase()"],
        ["tt", "db", "due cases … FOR UPDATE SKIP LOCKED"],
        ["tt", "ts", "advance_to_deliberation(case_id)"],
        ["ts", "js", "select_panel() — pure, seeded"],
        ["ts", "db", "seat_panel · UPDATE status='jury_deliberation'"],
        ["tt", "db", "COMMIT (else ROLLBACK)"],
        { note: "days 2–5 — each juror at speaks_at", from: "lp", to: "db" },
        ["lp", "tt", "run_due_jurors()"],
        ["tt", "js", "due_jurors(): speaks_at ≤ now, spoke_at NULL"],
        ["tt", "ts", "speak_as_juror(member)"],
        ["ts", "br", "deliberate(prompt, context)"],
        ["br", "ts", "{vote: enum, line}", 1],
        ["ts", "db", "INSERT comment dedupe_key='jury:<id>' · record_speech"],
        { note: "day 6 — verdict", from: "lp", to: "db" },
        ["lp", "tt", "advance_verdicts()"],
        ["tt", "ts", "advance_to_verdict(case_id)"],
        ["ts", "js", "tally(guilty, not_guilty, judge_lean)"],
        ["ts", "br", "generate('verdict') (+ 'sentence')"],
        ["ts", "db", "verdict comment · status='verdict_reached' · notify"]
      ]
    },
    bot: {
      actors: [["lp", "loop (SOCIAL_EVERY_TICKS)"], ["so", "social_tasks"], ["dc", "decide.py", "gold"], ["br", "app/brain", "gold"], ["ch", "chain → LLM", "dash"], ["db", "MySQL", "ok"]],
      steps: [
        ["lp", "so", "one_bot_social_action(tick)"],
        ["so", "db", "_next_bot: oldest last_social_action_at, SKIP LOCKED"],
        ["so", "dc", "decide_bot_action → 'file_case' (p=0.15)"],
        ["so", "dc", "decide_lawsuit_target → thing | topical | bot"],
        ["so", "br", "invent_lawsuit(…, require_llm=True)"],
        ["br", "ch", "_try_chain(structured=True)"],
        ["ch", "br", "{title, defendant, charges, body} (schema)", 1],
        { note: "no LLM / no structured output / failure → None → bot skips its turn", from: "so", to: "ch" },
        ["br", "so", "filing dict", 1],
        ["so", "db", "_names_a_registered_human(defendant)?"],
        ["so", "db", "cases_service.create_case (screened)"],
        ["so", "db", "record_event · UPDATE last_social_action_at"]
      ]
    }
  };
