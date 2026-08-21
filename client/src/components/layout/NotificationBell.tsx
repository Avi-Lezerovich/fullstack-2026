import { useState, type ReactNode } from "react";
import Badge from "@mui/material/Badge";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import ListItemButton from "@mui/material/ListItemButton";
import Menu from "@mui/material/Menu";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import NotificationsIcon from "@mui/icons-material/Notifications";
import GavelIcon from "@mui/icons-material/Gavel";
import FavoriteIcon from "@mui/icons-material/Favorite";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import RecordVoiceOverIcon from "@mui/icons-material/RecordVoiceOver";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";
import { useNavigate } from "react-router-dom";

import type { Notification, NotificationType } from "../../types";
import { relativeTime } from "../../utils/format";

const ICONS: Record<NotificationType, ReactNode> = {
  summons: <RecordVoiceOverIcon fontSize="small" />,
  testimony: <RecordVoiceOverIcon fontSize="small" />,
  verdict: <GavelIcon fontSize="small" />,
  like: <FavoriteIcon fontSize="small" />,
  comment: <ChatBubbleOutlineIcon fontSize="small" />,
  message: <MailOutlineIcon fontSize="small" />,
  moderation: <ShieldOutlinedIcon fontSize="small" />,
};

/** One human sentence per notification row. */
function describe(notification: Notification): string {
  const payload = notification.payload as Record<string, string | undefined>;
  const actor = notification.actor?.name;
  const title = payload.case_title;
  const inCase = title ? ` בתיק "${title}"` : "";

  switch (notification.type) {
    case "summons":
      return payload.outcome === "no_show"
        ? `לא הגעת למסור עדות${inCase}`
        : `${actor ?? "מישהו"} זימן/ה אותך לעדות${inCase}`;
    case "verdict":
      return `ניתן פסק דין${inCase}: ${payload.verdict === "guilty" ? "חייב" : "זכאי"}`;
    case "like":
      return `${actor ?? "מישהו"} אהב/ה את התביעה${title ? ` "${title}"` : ""}`;
    case "comment":
      return `${actor ?? "מישהו"} הגיב/ה${inCase}`;
    case "testimony":
      return `נמסרה עדות${inCase}`;
    case "message":
      return `הודעה חדשה מ${actor ?? "משתמש"}`;
    case "moderation":
      return payload.status === "banned"
        ? "החשבון שלך הושעה על ידי צוות הפיקוח"
        : payload.outcome === "dismissed"
          ? "הדיווח שהגשת נבדק ונדחה"
          : "תוכן שלך הוסר על ידי צוות הפיקוח";
    default:
      return "עדכון חדש";
  }
}

interface NotificationBellProps {
  notifications: Notification[];
  unreadCount: number;
  markRead: (ids?: number[]) => Promise<void>;
}

/**
 * The app-bar bell: an unread badge plus a dropdown of recent notifications.
 * State is owned by `useNotifications` in <TopBar> and passed in, so the bell
 * and the inbox badge share a single poll.
 */
const NotificationBell = ({ notifications, unreadCount, markRead }: NotificationBellProps) => {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const navigate = useNavigate();

  const open = (event: React.MouseEvent<HTMLElement>) => setAnchor(event.currentTarget);
  const close = () => setAnchor(null);

  const goTo = async (notification: Notification) => {
    close();
    if (!notification.is_read) await markRead([notification.id]);
    if (notification.case_id) navigate(`/cases/${notification.case_id}`);
    // A message notification carries its sender as the actor, which is all
    // the inbox needs to open the right thread.
    else if (notification.type === "message")
      navigate(notification.actor ? `/messages?to=${notification.actor.id}` : "/messages");
  };

  return (
    <>
      <IconButton
        onClick={open}
        aria-label="התראות"
        data-testid="notification-bell"
        sx={{ color: "primary.contrastText" }}
      >
        <Badge
          badgeContent={unreadCount}
          color="secondary"
          max={99}
          data-testid="notification-count"
        >
          <NotificationsIcon />
        </Badge>
      </IconButton>

      <Menu
        anchorEl={anchor}
        open={Boolean(anchor)}
        onClose={close}
        slotProps={{ paper: { sx: { width: 340, maxHeight: 420 } } }}
      >
        <Stack
          direction="row"
          justifyContent="space-between"
          alignItems="center"
          sx={{ px: 2, py: 1 }}
        >
          <Typography variant="subtitle2">התראות</Typography>
          {unreadCount > 0 && (
            <Button size="small" onClick={() => markRead()} data-testid="mark-all-read">
              סמן הכול כנקרא
            </Button>
          )}
        </Stack>
        <Divider />

        {notifications.length === 0 && (
          <Box sx={{ px: 2, py: 3, textAlign: "center" }}>
            <Typography variant="body2" color="text.secondary">
              אין התראות חדשות.
            </Typography>
          </Box>
        )}

        {notifications.map((notification) => (
          <ListItemButton
            key={notification.id}
            onClick={() => goTo(notification)}
            data-testid="notification-item"
            data-read={notification.is_read}
            sx={{
              alignItems: "flex-start",
              gap: 1,
              bgcolor: notification.is_read ? "transparent" : "rgba(60, 52, 137, 0.06)",
            }}
          >
            <Box sx={{ mt: 0.25, color: "text.secondary" }}>
              {ICONS[notification.type] ?? <NotificationsIcon fontSize="small" />}
            </Box>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2">{describe(notification)}</Typography>
              <Typography variant="caption" color="text.secondary">
                {relativeTime(notification.created_at)}
              </Typography>
            </Box>
          </ListItemButton>
        ))}
      </Menu>
    </>
  );
};

export default NotificationBell;
