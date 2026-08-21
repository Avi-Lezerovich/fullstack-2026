import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Avatar from "@mui/material/Avatar";
import Badge from "@mui/material/Badge";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import SendIcon from "@mui/icons-material/Send";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import { useSearchParams } from "react-router-dom";

import * as api from "../api";
import { EmptyState, ErrorNote, Loading } from "../components/common/StateViews";
import { useAsync } from "../hooks/useAsync";
import { useNotifications } from "../context/NotificationContext";
import type { Conversation, Message } from "../types";
import { initials, relativeTime } from "../utils/format";

/**
 * The inbox: conversations on one side, the open thread on the other.
 *
 * There is no polling here. New messages arrive as `message` notifications on
 * the stream the bell already listens to, so this page reloads off the same
 * transport rather than opening a second one — and it still works when the
 * stream has fallen back to polling, because both paths land in the same
 * context.
 */
const Messages = () => {
  const [params, setParams] = useSearchParams();
  const { notifications } = useNotifications();

  const conversations = useAsync(api.fetchConversations, []);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [thread, setThread] = useState<Message[]>([]);
  const [threadError, setThreadError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const bottom = useRef<HTMLDivElement | null>(null);

  const list = conversations.data?.conversations ?? [];
  const active = list.find((c) => c.id === activeId) ?? null;

  /**
   * `?to=<userId>` is how the rest of the app starts a conversation — from a
   * profile, or from a message notification. The id is resolved to the one
   * conversation for the pair, then dropped from the URL so a refresh does not
   * re-open it over whatever the user has since selected.
   */
  const to = params.get("to");
  useEffect(() => {
    if (!to) return;
    let cancelled = false;
    void (async () => {
      try {
        const id = await api.startConversation(Number(to));
        if (cancelled) return;
        setActiveId(id);
        await conversations.reload();
      } catch (err) {
        if (!cancelled) setThreadError(err instanceof Error ? err.message : "לא הצלחנו לפתוח שיחה.");
      } finally {
        if (!cancelled) setParams({}, { replace: true });
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [to]);

  const openThread = useCallback(async (conversationId: number) => {
    setThreadError(null);
    try {
      setThread(await api.fetchThread(conversationId));
    } catch (err) {
      setThread([]);
      setThreadError(err instanceof Error ? err.message : "לא הצלחנו לטעון את השיחה.");
    }
  }, []);

  useEffect(() => {
    if (activeId === null) {
      setThread([]);
      return;
    }
    void openThread(activeId);
  }, [activeId, openThread]);

  // The newest message notification. Its id changing is the signal that
  // something arrived — for this thread or another one.
  const latestMessageNotification = useMemo(
    () => notifications.find((n) => n.type === "message")?.id ?? 0,
    [notifications],
  );
  useEffect(() => {
    if (!latestMessageNotification) return;
    void conversations.reload();
    if (activeId !== null) void openThread(activeId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestMessageNotification]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest" });
  }, [thread]);

  const send = async (event: React.FormEvent) => {
    event.preventDefault();
    const body = draft.trim();
    if (!body || !active?.other) return;

    setSending(true);
    setThreadError(null);
    try {
      await api.sendMessage(active.other.id, body);
      setDraft("");
      await Promise.all([openThread(active.id), conversations.reload()]);
    } catch (err) {
      setThreadError(err instanceof Error ? err.message : "לא הצלחנו לשלוח את ההודעה.");
    } finally {
      setSending(false);
    }
  };

  if (conversations.loading && !conversations.data) return <Loading label="טוען את תיבת ההודעות…" />;
  if (conversations.error) return <ErrorNote message={conversations.error} />;

  return (
    <Stack
      direction={{ xs: "column", md: "row" }}
      spacing={2}
      alignItems="stretch"
      data-testid="messages-page"
    >
      {/* Below md only one pane is on screen at a time: the list, or the
          thread the user picked from it. */}
      <Paper
        sx={{
          width: { xs: "100%", md: 300 },
          flexShrink: 0,
          display: { xs: active ? "none" : "block", md: "block" },
          overflow: "hidden",
        }}
      >
        <Typography variant="h6" sx={{ px: 2, py: 1.5 }}>
          הודעות
        </Typography>
        <Divider />

        {list.length === 0 ? (
          <EmptyState
            title="אין עדיין שיחות"
            description="אפשר לפתוח שיחה מהפרופיל של כל אדם בחצר."
          />
        ) : (
          <List disablePadding sx={{ maxHeight: { md: "60vh" }, overflowY: "auto" }}>
            {list.map((conversation) => (
              <ConversationRow
                key={conversation.id}
                conversation={conversation}
                selected={conversation.id === activeId}
                onSelect={() => setActiveId(conversation.id)}
              />
            ))}
          </List>
        )}
      </Paper>

      <Paper
        sx={{
          flex: 1,
          minWidth: 0,
          display: { xs: active ? "flex" : "none", md: "flex" },
          flexDirection: "column",
        }}
        data-testid="message-thread"
      >
        {active ? (
          <>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ px: 2, py: 1.5 }}>
              <IconButton
                onClick={() => setActiveId(null)}
                sx={{ display: { xs: "inline-flex", md: "none" } }}
                aria-label="חזרה לרשימה"
              >
                <ArrowForwardIcon />
              </IconButton>
              <Avatar src={active.other?.avatar_url ?? undefined} sx={{ width: 32, height: 32 }}>
                {initials(active.other?.name ?? "?")}
              </Avatar>
              <Typography variant="subtitle1" fontWeight={700} noWrap sx={{ flex: 1 }}>
                {active.other?.name ?? "משתמש שנמחק"}
              </Typography>
              {active.other?.is_bot && <SmartToyIcon fontSize="small" color="disabled" />}
            </Stack>
            <Divider />

            <Box
              sx={{
                flex: 1,
                overflowY: "auto",
                px: 2,
                py: 2,
                minHeight: { xs: 240, md: "45vh" },
                maxHeight: { md: "45vh" },
              }}
            >
              {thread.length === 0 && !threadError && (
                <Typography color="text.secondary" align="center">
                  עוד לא נאמר כאן דבר. תתחיל/י.
                </Typography>
              )}
              <Stack spacing={1}>
                {thread.map((message) => (
                  <Bubble key={message.id} message={message} />
                ))}
              </Stack>
              <div ref={bottom} />
            </Box>

            <Divider />
            <Box component="form" onSubmit={send} sx={{ p: 1.5 }}>
              {threadError && <ErrorNote message={threadError} />}
              <Stack direction="row" spacing={1} alignItems="flex-end">
                <TextField
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="כתוב/י הודעה…"
                  multiline
                  maxRows={4}
                  fullWidth
                  size="small"
                  inputProps={{ "data-testid": "message-body", maxLength: 2000 }}
                  onKeyDown={(e) => {
                    // Enter sends; Shift+Enter is a newline, as everywhere else.
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void send(e as unknown as React.FormEvent);
                    }
                  }}
                />
                <IconButton
                  type="submit"
                  color="primary"
                  disabled={sending || !draft.trim()}
                  aria-label="שליחה"
                  data-testid="message-send"
                >
                  <SendIcon />
                </IconButton>
              </Stack>
            </Box>
          </>
        ) : (
          <EmptyState title="בחר/י שיחה" description="הרשימה מימין מרכזת את כל ההתכתבויות." />
        )}
      </Paper>
    </Stack>
  );
}; export default Messages;

const ConversationRow = ({
  conversation,
  selected,
  onSelect,
}: {
  conversation: Conversation;
  selected: boolean;
  onSelect: () => void;
}) => {
  return (
    <ListItemButton
      selected={selected}
      onClick={onSelect}
      data-testid="conversation-row"
      sx={{ alignItems: "flex-start", gap: 1.5 }}
    >
      <Badge
        color="secondary"
        badgeContent={conversation.unread_count}
        max={9}
        overlap="circular"
        anchorOrigin={{ vertical: "top", horizontal: "left" }}
      >
        <Avatar src={conversation.other?.avatar_url ?? undefined} sx={{ width: 36, height: 36 }}>
          {initials(conversation.other?.name ?? "?")}
        </Avatar>
      </Badge>

      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Typography variant="subtitle2" noWrap fontWeight={conversation.unread_count ? 700 : 500}>
          {conversation.other?.name ?? "משתמש שנמחק"}
        </Typography>
        <Typography variant="body2" color="text.secondary" noWrap>
          {conversation.last_message?.body ?? "—"}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {relativeTime(conversation.last_message?.created_at ?? null)}
        </Typography>
      </Box>
    </ListItemButton>
  );
};

const Bubble = ({ message }: { message: Message }) => {
  return (
    <Box
      data-testid="message-bubble"
      data-mine={message.is_mine}
      sx={{
        // The stack is a column, so alignSelf is the horizontal axis. Under
        // RTL `flex-end` is the left edge — where a Hebrew chat app puts the
        // messages you sent.
        alignSelf: message.is_mine ? "flex-end" : "flex-start",
        maxWidth: "80%",
        px: 1.5,
        py: 1,
        borderRadius: 2,
        bgcolor: message.is_mine ? "primary.main" : "action.hover",
        color: message.is_mine ? "primary.contrastText" : "text.primary",
      }}
    >
      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
        {message.body}
      </Typography>
      <Typography
        variant="caption"
        sx={{ display: "block", mt: 0.25, opacity: 0.7, textAlign: "start" }}
      >
        {relativeTime(message.created_at)}
      </Typography>
    </Box>
  );
};
